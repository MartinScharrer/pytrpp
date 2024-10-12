import json
import sys
from pygments import highlight, lexers, formatters
import time
from pathlib import Path

from api import TradeRepublicApi, CREDENTIALS_FILE
from utils import get_logger


def get_settings(tr):
    formatted_json = json.dumps(tr.settings(), indent=2)
    if sys.stdout.isatty():
        colorful_json = highlight(formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter())
        return colorful_json
    else:
        return formatted_json


def credentials(phone_no: str|None = None, pin: str|None = None, credentials_file: Path|str|None = None, store_file: bool = True) -> tuple[str, str]:
    """Process credentials to and from file if required"""
    write_required: bool = False
    # Read missing data from credential file
    if phone_no is None or pin is None:
        if credentials_file is None:
            raise ValueError
        lines = Path(credentials_file).read_text().splitlines()
        if phone_no is None:
            phone_no = lines[0].strip()
        else:
            write_required = True
        if pin is None:
            pin = lines[1].strip()
        else:
            write_required = True

    # store if any new information was given
    if write_required and store_file and credentials_file is not None:
        Path(credentials_file).write_text(f'{phone_no}\n{pin}\n')

    return phone_no, pin


def login(phone_no=None, pin=None, web=True, locale='de', save_cookies=True, credentials_file = None, cookies_file = None):
    '''
    If web is true, use web login method as else simulate app login.
    Check if credentials file exists else create it.
    If no parameters are set but are needed then ask for input
    '''
    log = get_logger(__name__)
    tr = TradeRepublicApi(phone_no=phone_no, pin=pin, locale=locale, save_cookies=save_cookies,
                          cookies_file=cookies_file, credentials_file=credentials_file)

    if web:
        # Use same login as app.traderepublic.com
        if tr.resume_websession():
            log.info('Web session resumed')
        else:
            try:
                countdown = tr.inititate_weblogin()
            except ValueError as e:
                log.fatal(str(e))
                exit(1)
            request_time = time.time()
            print('Enter the code you received to your mobile app as a notification.')
            print(f'Enter nothing if you want to receive the (same) code as SMS. (Countdown: {countdown})')
            code = input('Code: ')
            if code == '':
                countdown = countdown - (time.time() - request_time)
                for remaining in range(int(countdown)):
                    print(f'Need to wait {int(countdown-remaining)} seconds before requesting SMS...', end='\r')
                    time.sleep(1)
                print()
                tr.resend_weblogin()
                code = input('SMS requested. Enter the confirmation code:')
            tr.complete_weblogin(code)
    else:
        # Try to login. Ask for device reset if needed
        try:
            tr.login()
        except (KeyError, AttributeError):
            # old keyfile or no keyfile
            print('Error logging in. Reset device? (y)')
            confirmation = input()
            if confirmation == 'y':
                tr.initiate_device_reset()
                print('You should have received a SMS with a token. Please type it in:')
                token = input()
                tr.complete_device_reset(token)
                print('Reset done')
            else:
                print('Cancelling reset')
                exit(1)

    log.info('Logged in')
    # log.debug(get_settings(tr))
    return tr
