#!/usr/bin/python3
# coding=utf-8

class LoopNotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)

class AudioLoadError(Exception):
    def __init__(self, message):
        super().__init__(message)