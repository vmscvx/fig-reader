"""Проверка чтения kiwi на известных байтах: python test_kiwi.py (или pytest)."""
from readfig import R, decoder, schema


def test_primitives():
    assert R(b"\x7f").vu() == 127
    assert R(b"\x80\x01").vu() == 128
    assert [R(bytes([b])).vi() for b in (0, 1, 2, 3)] == [0, -1, 1, -2]  # зигзаг
    assert R(b"\x00").f() == 0.0
    assert R(b"\x7f\x00\x00\x00").f() == 1.0  # 0x3F800000 с экспонентой в младшем байте
    assert R(b"\xff" * 9).vu64() == 2**64 - 1  # девятый байт целиком
    assert R("ЁЖ\0".encode()).s() == "ЁЖ"


def test_message():
    # схема: message Message { int x = 1; string[] tags = 2; }
    sch = (b"\x01" + b"Message\0" + b"\x02" + b"\x02"
           + b"x\0" + b"\x05" + b"\x00" + b"\x01"       # тип ~2 (int) зигзагом = 5
           + b"tags\0" + b"\x0b" + b"\x01" + b"\x02")   # тип ~5 (string) = 11, массив
    data = b"\x01\x0e" + b"\x02\x02a\0b\0" + b"\x00"   # x = 7, tags = ["a", "b"]
    assert decoder(schema(sch))(data) == {"x": 7, "tags": ["a", "b"]}


if __name__ == "__main__":
    test_primitives(); test_message(); print("ok")
