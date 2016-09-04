#!/usr/bin/python3

import sys
import logging.handlers
from logging import *  # pylint: disable=W0614,W0401
import queue

class WrappingFormatter(Formatter):
    def formatMessage(self, record):
        record.message = record.message.replace('\n', '\n\t')
        return super().formatMessage(record)


class LogManager(object):
    def __init__(self, runtime_settings):
        self.runtime_settings = runtime_settings

        self.root_logger = None
        self.queue = None
        self.queue_handler = None
        self.queue_listener = None

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def setup(self):
        captureWarnings(True)

        # Remove all existing log handlers and install a single QueueHandler.
        self.root_logger = getLogger()
        for handler in self.root_logger.handlers:
            self.root_logger.removeHandler(handler)
        self.root_logger.setLevel(DEBUG)

        self.queue = queue.Queue()
        self.queue_handler = logging.handlers.QueueHandler(self.queue)
        self.root_logger.addHandler(self.queue_handler)

        # Make loggers of 3rd party modules less noisy.
        for other in ('quamash', 'vext'):
            getLogger(other).setLevel(WARNING)

        # Create a QueueListener that reads from the queue and sends log
        # records to the actual log handlers.
        handlers = []

        handlers.append(self.create_stderr_logger())

        if self.runtime_settings.log_file:
            handlers.append(self.create_file_logger())

        self.queue_listener = logging.handlers.QueueListener(
            self.queue, *handlers, respect_handler_level=True)
        self.queue_listener.start()

    def cleanup(self):
        if self.queue_handler is not None:
            self.root_logger.removeHandler(self.queue_handler)
            self.queue_handler = None

        if self.queue_listener is not None:
            self.queue_listener.stop()
            self.queue_listener = None

        if self.queue is not None:
            assert self.queue.empty()
            self.queue = None

    def create_stderr_logger(self):
        log_level = {
            'debug': DEBUG,
            'info': INFO,
            'warning': WARNING,
            'error': ERROR,
            'critical': CRITICAL,
            }[self.runtime_settings.log_level]
        handler = StreamHandler(sys.stderr)
        handler.setLevel(log_level)
        handler.setFormatter(
            WrappingFormatter(
                '%(levelname)-8s:%(process)5s:%(thread)08x:%(name)s: %(message)s'))
        return handler

    def create_file_logger(self):
        handler = logging.handlers.RotatingFileHandler(
            self.runtime_settings.log_file,
            maxBytes=10 * 2**20,
            backupCount=9,
            encoding='utf-8')
        handler.setLevel(DEBUG)
        handler.setFormatter(WrappingFormatter(
            '%(asctime)s\t%(levelname)s\t%(process)s\t%(thread)08x\t%(name)s\t%(message)s',
            '%Y%m%d-%H%M%S'))
        return handler
