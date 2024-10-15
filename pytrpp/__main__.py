#!/usr/bin/env python3
import logging

try:
    from main import main
except ImportError:
    from .main import main


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log = logging.getLogger(__name__)
        log.info('Exiting...')
        exit()
    except Exception as e:
        log = logging.getLogger(__name__)
        log.fatal(e)
        raise
