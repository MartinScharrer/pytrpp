[![GitHub tag (with filter)](https://img.shields.io/github/v/tag/martin_scharrer/pytrpp?style=for-the-badge&link=https%3A%2F%2Fgithub.com%2Fmartin_scharrer%2Fpytrpp%2Ftags)](https://github.com/martin_scharrer/pytrpp/tags)
[![PyPI build and publish](https://img.shields.io/github/actions/workflow/status/martin_scharrer/pytrpp/publish-pypi.yml?link=https%3A%2F%2Fgithub.com%2Fmartin_scharrer%2Fpytrpp%2Factions%2Fworkflows%2Fpublish-pypi.yml&style=for-the-badge)](https://github.com/martin_scharrer/pytrpp/actions/workflows/publish-pypi.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/pytrpp?link=https%3A%2F%2Fpypi.org%2Fproject%2Fpytrpp%2F&style=for-the-badge)](https://pypi.org/project/pytrpp/)

# pytrpp: Download TradeRepublic files and export data to Portfolio Performance

This is a library for the private API of the Trade Republic online brokerage.
This package and its authors are not affiliated with Trade Republic Bank GmbH.

Files can be produced to import orders and other transactions into Portfolio Performance: 
*An open source tool to calculate the overall performance of an investment portfolio - across all accounts - using True-Time Weighted Return or Internal Rate of Return.*
https://www.portfolio-performance.info/.
The package authors are not affiliated with Portfolio Performance.


## Installation

Install release from PyPI with `pip install pytrpp`

Or install from git repo like so: `pip install git+https://github.com/martin_scharrer/pytrpp`


## Usage
Recommended usages:
 * ``pytrpp -n PHONE_NO -p PIN -D TARGET_DIR``
 * ``pytrpp -C CREDENTIALS_FILE -D TARGET_DIR`` \
   The credential file consists of two lines with the phone number followed by the PIN.


Full usage information:
````
usage: pytrpp [-h] [-v {warning,info,debug}] [-V] [-n PHONE_NO] [-p PIN]
              [-l LOCALE] [-D DIR] [-K COOKIES_FILE] [-C CREDENTIALS_FILE]
              [-E EVENTS_FILE] [-P PAYMENTS_FILE] [-O ORDERS_FILE]
              [-F DOCS_DIR] [-d DAYS | -s DATE | -r FILE] [--workers WORKERS]

Use "pytrpp command_name --help" to get detailed help to a specific command

options:
  -h, --help             show this help message and exit
  -v {warning,info,debug}, --verbosity {warning,info,debug}
                         Set verbosity level (default: info)
  -V, --version          Print version information and quit
  -n PHONE_NO, --phone_no PHONE_NO
                         TradeRepublic phone number (international format)
  -p PIN, --pin PIN      TradeRepublic pin
  -l LOCALE, --locale LOCALE
                         Locale setting (e.g. "en" for English, "de" for
                         German)
  -D DIR, --dir DIR      Main directory to use. Special path can be set using
                         the following options.
  -K COOKIES_FILE, --cookies-file COOKIES_FILE
                         Cookies file
  -C CREDENTIALS_FILE, --credentials-file CREDENTIALS_FILE
                         Credential file
  -E EVENTS_FILE, --events-file EVENTS_FILE
                         Events file to store
  -P PAYMENTS_FILE, --payments-file PAYMENTS_FILE
                         Payments file to store
  -O ORDERS_FILE, --orders-file ORDERS_FILE
                         Orders file to store
  -F DOCS_DIR, --docs-dir DOCS_DIR
                         Directory to download files to
  --workers WORKERS      Number of workers for parallel downloading

Date Range:
  Control date range to include (mutually exclusive):

  -d DAYS, --last-days DAYS
                         Number of last days to include
  -s DATE, --since DATE  Include only entry since this date
  -r FILE, --since-ref FILE
                         Include only entry newer than the modified date of
                         this file
````

## Authentication

Currently only web login (simulating a browser) is supported.

The phone number and the PIN must be provided. A login code is then generated as second factor on the connected
smartphone which also needs to be entered. The login can be buffered using a cookie file, so multiple runs will
only require the login code once until the cookie expires.

