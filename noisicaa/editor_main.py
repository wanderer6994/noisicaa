#!/usr/bin/python3

import argparse
import asyncio
import sys
import time

from .constants import EXIT_SUCCESS, EXIT_RESTART, EXIT_RESTART_CLEAN
from .runtime_settings import RuntimeSettings
from . import logging
from .core import process_manager


class Main(object):
    def __init__(self):
        self.runtime_settings = RuntimeSettings()
        self.paths = []
        self.event_loop = asyncio.get_event_loop()
        self.manager = process_manager.ProcessManager(self.event_loop)
        self.manager.server.add_command_handler(
            'CREATE_PROJECT_PROCESS', self.handle_create_project_process)

    def run(self, argv):
        self.parse_args(argv)

        logging.init(self.runtime_settings)
        self.logger = logging.getLogger(__name__)

        if self.runtime_settings.dev_mode:
            import pyximport
            pyximport.install()

        try:
            self.event_loop.run_until_complete(self.run_async())
        finally:
            self.event_loop.stop()
            self.event_loop.close()

    async def run_async(self):
        async with self.manager:
            while True:
                next_retry = time.time() + 5

                proc = await self.manager.start_process(
                    'ui', 'noisicaa.ui.ui_process.UIProcess',
                    runtime_settings=self.runtime_settings,
                    paths=self.paths)
                await proc.wait()

                if proc.returncode == EXIT_RESTART:
                    self.runtime_settings.start_clean = False

                elif proc.returncode == EXIT_RESTART_CLEAN:
                    self.runtime_settings.start_clean = True

                elif proc.returncode == EXIT_SUCCESS:
                    return proc.returncode

                else:
                    self.logger.error(
                        "UI Process terminated with exit code %d",
                        proc.returncode)
                    if self.runtime_settings.dev_mode:
                        self.runtime_settings.start_clean = False

                        delay = next_retry - time.time()
                        if delay > 0:
                            self.logger.warning(
                                "Sleeping %.1fsec before restarting.",
                                delay)
                            await asyncio.sleep(delay)
                    else:
                        return proc.returncode

    def parse_args(self, argv):
        parser = argparse.ArgumentParser(
            prog=argv[0])
        parser.add_argument(
            'path',
            nargs='*',
            help="Project file to open.")
        self.runtime_settings.init_argparser(parser)
        args = parser.parse_args(args=argv[1:])
        self.runtime_settings.set_from_args(args)
        self.paths = args.path

    async def handle_create_project_process(self, uri):
        # TODO: keep map of uri->proc, only create processes for new
        # URIs.
        proc = await self.manager.start_process(
            'project', 'noisicaa.music.project_process.ProjectProcess')
        return proc.address


if __name__ == '__main__':
    sys.exit(Main().run(sys.argv))
