import datetime


def __main__():
    parser = DpsParser
    p = r"C:\Users\SP\AppData\Roaming\XivAlexander\Dump\Dump_20211023_111519_579_238.log"
    with open(p) as fp:
        for line in fp:
            ts = datetime.datetime(int(line[0:4], 10), int(line[5:7], 10), int(line[8:10], 10),
                                   int(line[11:13], 10), int(line[14:16], 10), int(line[17:19], 10),
                                   int(line[20:23], 10) * 1000)
            is_recv = line[24] == '>'
            data = bytearray.fromhex(line[25:])
            parser.feed(ts, is_recv, data)
    return 0


if __name__ == "__main__":
    exit(__main__())
