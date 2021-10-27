import contextlib
import ctypes
import dataclasses
import ipaddress
import struct
import typing

import pyshark
import sys

from pyxivdata.network.packet import PacketHeader


@dataclasses.dataclass(order=True, frozen=True)
class AddressPair:
    addr1: ipaddress.IPv4Address
    port1: int
    addr2: ipaddress.IPv4Address
    port2: int

    @classmethod
    def from_pair(cls, addr1: ipaddress.IPv4Address, port1: int, addr2: ipaddress.IPv4Address, port2: int):
        if addr1 > addr2 or (addr1 == addr2 and port1 > port2):
            addr1, addr2 = addr2, addr1
            port1, port2 = port2, port1

        return cls(addr1, port1, addr2, port2)


class ConnectionStream:
    addr: ipaddress.IPv4Address
    port: int
    seq: typing.Optional[int]
    fin: bool

    def __init__(self, addr: ipaddress.IPv4Address, port: int, seq: typing.Optional[int]):
        self.addr = addr
        self.port = port
        self.seq = seq
        self.fin = False
        self.pending = {}
        self.assembled = []
        self.seqs = []

    def later(self, data: typing.Union[bytes, bytearray, memoryview]):
        self.assembled = [data]

    def feed(self, seq: int, nxtseq: int, data: typing.Optional[bytes]):
        self.pending[seq] = (data or b""), nxtseq
        while True:
            data = self.pending.pop(self.seq, None)
            if data is None:
                break
            data, nxtseq = data
            self.seqs.append(self.seq)
            self.seq = nxtseq
            self.assembled.append(data)
        data = b"".join(self.assembled)
        self.assembled = []
        if data:
            yield data


class Connection:
    stream1: ConnectionStream
    stream2: ConnectionStream

    SRC = object()
    DST = object()

    def __init__(self, addr1: ipaddress.IPv4Address, port1: int, addr2: ipaddress.IPv4Address, port2: int,
                 addr1seq: int):
        self.stream1 = ConnectionStream(addr1, port1, addr1seq)
        self.stream2 = ConnectionStream(addr2, port2, None)

    def set_fin_ack(self, addr: ipaddress.IPv4Address, port: int):
        if addr == self.stream1.addr and port == self.stream1.port:
            self.stream1.fin = True
        elif addr == self.stream2.addr and port == self.stream2.port:
            self.stream2.fin = True
        return self.stream1.fin and self.stream2.fin

    def _feed(self, srcaddr: ipaddress.IPv4Address, srcport: int, seq: int, nxtseq: int,
              data: typing.Optional[bytes]):
        if srcaddr == self.stream1.addr and srcport == self.stream1.port:
            for x in self.stream1.feed(seq, nxtseq, data):
                yield Connection.SRC, self.stream1, x

        elif srcaddr == self.stream2.addr and srcport == self.stream2.port:
            for x in self.stream2.feed(seq, nxtseq, data):
                yield Connection.DST, self.stream2, x

    def process(self, srcaddr: ipaddress.IPv4Address, srcport: int,
                seq: int, nxtseq: int, data: typing.Optional[bytes]):
        for who, stream, assembled in self._feed(srcaddr, srcport, seq, nxtseq, data):
            assembled = bytearray(assembled)

            ptr = 0
            while ptr < len(assembled):
                if ptr + ctypes.sizeof(PacketHeader) > len(assembled):
                    break
                packet_header = PacketHeader.from_buffer(assembled, ptr)
                if ptr + packet_header.size > len(assembled):
                    break

                if bytes(packet_header.signature) not in (PacketHeader.SIGNATURE_1, PacketHeader.SIGNATURE_2):
                    yield who, assembled[ptr:ptr + 1]
                    ptr += 1
                else:
                    yield who, assembled[ptr:ptr + packet_header.size]
                    ptr += packet_header.size

            if ptr < len(assembled):
                stream.later(assembled[ptr:])


def __main__():
    path = r"D:\OneDrive\Misc\xivcapture\Network_22106_20211025"
    c = pyshark.FileCapture(fr"{path}.pcapng")

    connections = {}
    with contextlib.ExitStack() as exit_stack:
        files: typing.Dict[typing.Tuple[ipaddress.IPv4Address, int], typing.BinaryIO] = {}

        for i, pkt in enumerate(c):
            print(f"\r[{i:>7}] ", end="")
            if i % 100 == 0:
                sys.stdout.flush()

            try:
                srcaddr, srcport = ipaddress.ip_address(pkt.ip.src), int(pkt.tcp.srcport)
                dstaddr, dstport = ipaddress.ip_address(pkt.ip.dst), int(pkt.tcp.dstport)
            except AttributeError:
                continue

            addr_pair = AddressPair.from_pair(srcaddr, srcport, dstaddr, dstport)
            connection: Connection = connections.get(addr_pair, None)

            tcp_flags = pkt.tcp.flags.hex_value

            if tcp_flags & 0x02:  # SYN
                if tcp_flags & 0x10:  # ACK
                    if connection is None:
                        continue
                    connection.stream2.seq = int(pkt.tcp.seq)
                else:
                    connection = connections[addr_pair] = Connection(srcaddr, srcport, dstaddr, dstport,
                                                                     int(pkt.tcp.seq))
                    print(f"\r[{i:>7}] New connection {addr_pair}")
                    # noinspection PyTypeChecker
                    fp = exit_stack.enter_context(
                        open(rf"{path}\{dstaddr}.{dstport}.log", "wb"))
                    files[connection.stream2.addr, connection.stream2.port] = fp
            if connection is None:
                continue  # don't know, don't care

            if tcp_flags & 0x04:  # RST
                del connections[addr_pair]
                continue

            if tcp_flags & 0x11 == 0x11:  # FIN ACK
                if connection.set_fin_ack(srcaddr, srcport):
                    del connections[addr_pair]
                    continue

            try:
                data = pkt.tcp.payload.binary_value
            except AttributeError:
                data = b""
            fp = files[connection.stream2.addr, connection.stream2.port]
            for who, packet in connection.process(srcaddr, srcport, int(pkt.tcp.seq), int(pkt.tcp.nxtseq), data):
                hdr = struct.pack("<cI", b'<' if who is Connection.DST else b'>', len(packet))
                fp.write(hdr)
                print(fp.tell(), len(packet))
                fp.write(packet)

    return 0


if __name__ == "__main__":
    exit(__main__())
