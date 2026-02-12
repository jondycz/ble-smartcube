"""Minimal LZString decoder for encoded URI components."""

from __future__ import annotations

from typing import Callable, Dict, List


def _bit_reverse_16(value: int) -> int:
    value = ((value << 1) & 0xAAAA) | ((value >> 1) & 0x5555)
    value = ((value << 2) & 0xCCCC) | ((value >> 2) & 0x3333)
    value = ((value << 4) & 0xF0F0) | ((value >> 4) & 0x0F0F)
    value = ((value << 8) & 0xFF00) | ((value >> 8) & 0x00FF)
    return value


def _alpha_reverse(alphabet: str) -> str:
    chars: List[str] = []
    for i in range(64):
        chars.append(alphabet[_bit_reverse_16(i) >> 10])
    return "".join(chars)


def _get_base_value(alphabet: str, cache: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    if alphabet not in cache:
        cache[alphabet] = {alphabet[i]: i for i in range(len(alphabet))}
    return cache[alphabet]


def _decompress(length: int, bits_per_char: int, get_next_value: Callable[[int], int]) -> str:
    dictionary: List[str | int] = []
    enlarge_in = 4
    dict_size = 4
    num_bits = 3
    result: List[str] = []
    data = {"val": 0, "remain": 0, "index": 0}

    def next_bits(n_bits: int) -> int:
        bits = 0
        offset = 0
        while n_bits > offset:
            n_fill = min(n_bits - offset, data["remain"])
            bits |= (data["val"] & ((1 << n_fill) - 1)) << offset
            offset += n_fill
            data["remain"] -= n_fill
            data["val"] >>= n_fill
            if data["remain"] == 0:
                data["remain"] = bits_per_char
                data["val"] = get_next_value(data["index"])
                data["index"] += 1
        return bits

    for i in range(3):
        dictionary.append(i)

    next_val = next_bits(2)
    if next_val == 0:
        c = chr(next_bits(8))
    elif next_val == 1:
        c = chr(next_bits(16))
    else:
        return ""

    dictionary.append(c)
    w = c
    result.append(c)

    while True:
        if data["index"] > length:
            return ""

        c_val = next_bits(num_bits)
        if c_val == 0:
            dictionary.append(chr(next_bits(8)))
            c_val = dict_size
            dict_size += 1
            enlarge_in -= 1
        elif c_val == 1:
            dictionary.append(chr(next_bits(16)))
            c_val = dict_size
            dict_size += 1
            enlarge_in -= 1
        elif c_val == 2:
            return "".join(result)

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1

        if c_val < dict_size:
            entry = dictionary[c_val]
        elif c_val == dict_size:
            entry = w + w[0]
        else:
            return ""

        result.append(entry)
        dictionary.append(w + entry[0])
        dict_size += 1
        enlarge_in -= 1
        w = entry

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1


def decompress_from_encoded_uri_component(value: str | None) -> str:
    """Decompress an encoded URI component string using LZString."""
    if value is None:
        return ""
    if value == "":
        return ""

    value = value.replace(" ", "+")
    key_str_uri_safe = _alpha_reverse("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-$")
    cache: Dict[str, Dict[str, int]] = {}
    char_map = _get_base_value(key_str_uri_safe, cache)

    return _decompress(len(value), 6, lambda index: char_map[value[index]])
