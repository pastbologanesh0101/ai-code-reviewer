"""A deliberately messy sample module used to demonstrate ai-code-reviewer.

Every function/class in this file exists purely to trigger one or more
findings from review.py. Do not use this file as an example of good style!
"""

import os
import sys
import json
import re


def add(a, b):
    return a + b


def add2(a, b):
    return a + b


def process(data, x=[], y={}, flag=None, mode=None, verbose=None):
    if flag:
        if mode == "a":
            if verbose:
                if data:
                    if len(data) > 0:
                        for item in data:
                            if item:
                                print(item)
    x.append(1)
    return x


def compute_score(a, b, c, d, e, f, g):
    total = 0
    if a > 0:
        total += 1
    elif a < 0:
        total -= 1
    if b > 0 and c > 0:
        total += 1
    if d or e:
        total += 1
    for i in range(f):
        if i % 2 == 0:
            total += 1
        else:
            total -= 1
    while g > 0:
        g -= 1
        if g == 5:
            total += 5
        elif g == 3:
            total -= 3
    try:
        result = total / g
    except:
        result = 0
    return result


def long_function():
    total = 0
    total += 1
    total += 2
    total += 3
    total += 4
    total += 5
    total += 6
    total += 7
    total += 8
    total += 9
    total += 10
    total += 11
    total += 12
    total += 13
    total += 14
    total += 15
    total += 16
    total += 17
    total += 18
    total += 19
    total += 20
    total += 21
    total += 22
    total += 23
    total += 24
    total += 25
    total += 26
    total += 27
    total += 28
    total += 29
    total += 30
    total += 31
    total += 32
    total += 33
    total += 34
    total += 35
    total += 36
    total += 37
    total += 38
    total += 39
    total += 40
    total += 41
    total += 42
    total += 43
    total += 44
    total += 45
    total += 46
    total += 47
    total += 48
    total += 49
    total += 50
    total += 51
    return total


class Helper:
    def do_work(self, n):
        q = n * 2
        z = q + 1
        return z


def risky():
    try:
        return json.loads("{}")
    except:
        pass
