import json
import re
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, Context
from typing import Callable, Any
from pathlib import Path

try:
    from trdl import get_timestamp
except ImportError:
    from .trdl import get_timestamp

RE_ISIN = re.compile(r"^[A-Z]{2}-?[\dA-Z]{9}-?\d$")


class Amount:
    def __init__(self, value: str|Decimal, currency: str, fraction_digits: int|None = None) -> None:
        self.value = Decimal(value)
        if fraction_digits is not None:
            self.value = self.value.quantize(Decimal('1.' + '0' * int(fraction_digits)))
        self.currency = currency

    def __format__(self, format_spec: str):
        if format_spec == ',':
            return str(self.value).replace('.', ',')
        elif format_spec == '.':
            return str(self.value)
        else:
            return format(self.value, format_spec)

    def __repr__(self):
        return f'{repr(self.value)} {self.currency}'

    @classmethod
    def zero(cls, currency='EUR'):
        return cls(Decimal('0.00'), currency)


def amount(event: dict) -> Amount | None:
    """Extract amount from event."""
    try:
        amount_dict = event['amount']
        return Amount(amount_dict['value'], amount_dict['currency'], amount_dict['fractionDigits'])
    except KeyError:
        return None


def text_amount(text: str) -> Amount | None:
    if text == 'Gratis':
        return Amount.zero()
    try:
        value, currency = text.split(" ", 2)
        value = value.replace('.', '').replace(',', '.').lstrip('+- ')
    except ValueError:
        currency, value = text[0], text[1:]
    currency = {'€': 'EUR', '$': 'USD'}.get(currency, ascii(currency))
    return Amount(value, currency)


class SecurityTransaction:
    """Security transaction of any type"""

    def __init__(self, name, isin, shares, value, price, costs, taxes) -> None:
        self.name = name
        self.isin = isin
        self.shares = shares
        self.value = value
        self.price = price
        self.costs = costs
        self.taxes = taxes

        # SecurityTransaction(name='', isin=isin,
        #                    shares=transaction['Anteile'], price=transaction['Aktienkurs'],
        #                   costs=transaction['Gebühr'], value=transaction['Gesamt'],
        #                   taxes=transaction.get('Steuern', Value.zero()))


class Event:
    pass


class TransactionEvent(Event):

    def get_isin(self, event: dict):
        try:
            sections = event['details']['sections']
            for section in sections:
                action = section.get('action')
                if action:
                    if action['type'] == 'instrumentDetail':
                        return action['payload']
        except KeyError:
            pass
        # Otherwise try to extract it from the icon
        try:
            icon = event['icon'].split('/', 3)[1]
            # ISIN is either 12 wide without dashes or 14 wide with dashes

            if RE_ISIN.match(icon):
                return icon
            else:
                pass
        except (TypeError, ValueError):
            pass
        return ''

    def get_transaction(self, event: dict):
        transaction = {}
        try:
            sections = event['details']['sections']
            for section in sections:
                if section.get('title') in ('Transaktion', 'Geschäft'):
                    for data in section['data']:
                        title = data['title']
                        text = data['detail']['text']
                        if title == 'Aktion':
                            text = Decimal(text)
                        elif title in ('Gebühr', 'Steuern'):
                            if text.lower() == 'kostenlos':
                                text = Amount.zero()
                            else:
                                text = text_amount(text)
                        elif title in ('Aktienkurs', 'Anteilspreis'):
                            title = 'Preis'
                            text = text_amount(text)
                        elif title in ('Gesamt', 'Tilgung', 'Coupon Zahlung'):
                            text = text_amount(text)
                        elif title in ('Anteile', 'Aktien'):
                            title = 'Anteile'
                            text = Decimal(text.replace(',', '.'))
                        elif title == 'Dividende pro Aktie':
                            title = 'Dividende je Aktie'
                        else:
                            pass

                        transaction[title] = text
        except KeyError:
            pass
        return transaction

    def get_section(self, event: dict, *section_titles: tuple[str]) -> dict | None:
        transaction = {}
        try:
            sections = event['details']['sections']
            for section in sections:
                if section.get('title') in section_titles:
                    section_data = {
                        data['title']: data['detail']['text']
                        for data in section['data']
                    }
                    return section_data
        except KeyError:
            return


class Unknown(Event):
    def __init__(self, event: dict):
        self.event = deepcopy(event)

    def __repr__(self):
        return f'Unknown({self.event["eventType"]})'


class Ignore(Event):
    def __init__(self, event: dict):
        self.event = deepcopy(event)

    def __repr__(self):
        return f'Ignore({self.event["eventType"]})'


class Investment(TransactionEvent):
    note: str
    type: str

    TYPES = {
        'Round up': 'Kauf',
        'Sparplan': 'Kauf',
        'Saveback': 'Einlieferung',
        'Wertpapiertransfer': 'Einlieferung',
        'Kauf': 'Kauf',
        'Verkauf': 'Verkauf',
    }

    def __init__(self, event: dict):
        self.dt: datetime = get_timestamp(event['timestamp'])
        self.value: Amount = amount(event)
        if event.get('title', '').startswith('Anleihe'):
            self.note = 'Anleihe'
        self.isin: str = self.get_isin(event)
        transaction = self.get_transaction(event)
        self.price = transaction.get('Preis')
        self.taxes = transaction.get('Steuern', Amount.zero())
        self.costs = transaction.get('Gebühr', Amount.zero())
        if self.value is None:
            self.value = transaction.get('Gesamt', Amount.zero())
        overview = self.get_section(event, 'Übersicht')
        for t in ('Asset', 'Anteil'):
            self.name = overview.get(t)
            if self.name is not None:
                break
        try:
            self.type
        except AttributeError:
            for t in ('Ordertyp', 'Orderart', 'Auftragsart'):
                ty = overview.get(t)
                if ty is not None:
                    break
            self.type = self.TYPES.get(ty, ty)
        self.shares = transaction.get('Anteile')
        if self.shares is None:
            self.shares = 1


    @staticmethod
    def csv_header(sep=';'):
        return f'Wert{sep}Buchungswährung{sep}Datum{sep}Uhrzeit{sep}Typ{sep}Notiz{sep}Gebühren{sep}Steuern{sep}ISIN{sep}Wertpapiername{sep}Stück\n'

    def csv(self, sep=';', decimal=','):
        dt = self.dt.astimezone()
        return (
            f'{self.value:{decimal}}{sep}{self.value.currency}{sep}{dt:%d.%m.%Y}{sep}'
            f'{dt:%H:%M:%S}{sep}{self.type}{sep}{self.note}{sep}{self.costs:{decimal}}{sep}{self.taxes:{decimal}}{sep}'
            f'{self.isin}{sep}{self.name}{sep}{str(self.shares).replace(".", ",")}\n'
        )


class Payment(Event):
    note: str
    type: str

    def __init__(self, event: dict):
        self.dt: datetime = get_timestamp(event['timestamp'])
        self.value: Amount = amount(event)

    def csv(self, sep=';', decimal=','):
        dt = self.dt.astimezone()
        try:
            taxes = f'{self.taxes:{decimal}}'
        except AttributeError:
            taxes = ''
        return f'{str(self.value.value).replace(".", ",")}{sep}{self.value.currency}{sep}{dt:%d.%m.%Y}{sep}{dt:%H:%M:%S}{sep}{self.type}{sep}{self.note}{sep}{taxes}{sep}{sep}{sep}\n'

    @staticmethod
    def csv_header(sep=';'):
        return f'Wert{sep}Buchungswährung{sep}Datum{sep}Uhrzeit{sep}Typ{sep}Notiz{sep}Steuern{sep}ISIN{sep}Wertpapiername{sep}Stück\n'


class RoundUp(Investment):
    """benefits_spare_change_execution"""
    note = 'Round-up'

    def __repr__(self):
        return f'RoundUp(asset="{self.asset}", value={self.value}, dt="{self.dt}", isin="{self.isin}", transaction="{self.transaction}")'


class AccountTransferIncoming(Investment):
    note = 'Eingehender Wertpapierübertrag'
    type = 'Einlieferung'

    def __init__(self, event: dict):
        super().__init__(event)
        if self.value is None:
            self.value = Amount.zero()


class SecuritiesTransferOutgoing(Investment):
    note = 'Ausgehender Wertpapierübertrag'
    type = 'Auslieferung'

    def __init__(self, event: dict):
        self.dt: datetime = get_timestamp(event['timestamp'])
        self.isin: str = self.get_isin(event)
        overview = self.get_section(event, 'Übersicht', 'Overview')
        for t in ('Asset', 'Anteil'):
            self.name = overview.get(t)
            if self.name is not None:
                break
        self.shares = overview.get('Aktien')
        if self.shares is None:
            self.shares = 1
        self.costs = Amount.zero()
        self.taxes = Amount.zero()
        self.value = Amount.zero()


class SavingsPlanExec(Investment):
    note = 'Sparplan'


class SaveBack(Investment):
    note = 'SaveBack'


class Order(Investment):
    note = 'Wertpapierorder'


class StockPerkRefunded(AccountTransferIncoming):
    note = 'Gratisaktie'

    def __init__(self, event: dict):
        super().__init__(event)
        self.type = "Einlieferung"


class CardTransaction(Payment):
    type = 'Entnahme'
    note = 'Kartenzahlung'

    def __init__(self, event: dict):
        super().__init__(event)
        self.note += f": {event['title']}"

    def __repr__(self):
        return f'CardTransaction(value={self.value}, dt="{self.dt}", note="{self.note}")'


class PaymentInbound(Payment):
    type = 'Einlage'
    note = 'Eingehende Überweisung'

    def __repr__(self):
        return f'PaymentInbound(value={self.value}, dt="{self.dt}"")'


class PaymentInboundSepaDirectDebit(PaymentInbound):
    note = 'Eingehende Lastschrift'


class PaymentOutbound(Payment):
    type = 'Entnahme'
    note = 'Ausgehende Überweisung'

    def __repr__(self):
        return f'PaymentOutbound(value={self.value}, dt="{self.dt}"")'


class Dividend(Payment, TransactionEvent):
    """Dividend payout"""
    type = 'Dividende'
    note = 'Dividende'

    def __init__(self, event: dict):
        super().__init__(event)
        self.isin: str = self.get_isin(event)
        transaction = self.get_transaction(event)
        self.shares = transaction['Anteile']
        self.dividend_per_share = transaction.get('Dividende je Aktie')
        self.taxes = transaction.get('Steuern', Amount.zero())
        self.name = event['title']

    def csv(self, sep=';'):
        s = super().csv(sep).rstrip(f'\n{sep}')
        return f'{s}{sep}{self.taxes}{sep}{self.isin}{sep}"{self.name}"{sep}{self.shares}\n'

    def __repr__(self):
        return f'{self.__class__.__name__}(value={self.value}, dt="{self.dt}"")'


class CouponPayment(Payment, TransactionEvent):
    type = 'Dividende'
    note = 'Coupon Zahlung'

    def __init__(self, event: dict):
        super().__init__(event)
        self.isin: str = self.get_isin(event)
        transaction = self.get_transaction(event)
        self.shares = 1
        self.value = transaction['Coupon Zahlung']
        self.taxes = transaction.get('Steuern', Amount.zero())
        self.name = f'{event["title"]}: Coupon {transaction["Coupon"]}'

    def csv(self, sep=';'):
        s = super().csv(sep).rstrip(f'\n{sep}')
        return f'{s}{sep}{self.taxes}{sep}{self.isin}{sep}"{self.name}"{sep}{self.shares}\n'


class InterestPayout(Payment, TransactionEvent):
    type = 'Zinsen'
    note = 'Zinsen'

    def __init__(self, event: dict):
        super().__init__(event)
        transaction = self.get_transaction(event)
        self.taxes = transaction.get('Steuern', Amount.zero())

    def __repr__(self):
        return f'Credit(value={self.value}, dt="{self.dt}"")'


class TaxRefund(Payment):
    type = 'Steuerrückerstattung'
    note = 'Steuerrückerstattung'


class CardRefund(CardTransaction):
    type = 'Einlage'
    note = 'Kartenrückzahlung'


class CardOriginalCreditTransaction(CardTransaction):
    type = 'Einlage'
    note = 'Kartenrückzahlung'


class CardWithdrawal(CardTransaction):
    type = 'Entnahme'
    note = 'Geldautomat'

    def __init__(self, event: dict):
        super().__init__(event)
        self.note += f" {event['subtitle']}"


class CardOrderBilled(Payment):
    type = 'Gebühren'
    note = 'Kartengebühr'


class BondRepayment(Investment):
    note = 'Anleihe'

    def __init__(self, event: dict):
        super().__init__(event)
        self.type = 'Verkauf'


class Converter:
    event_types: dict[str, Callable[[dict], Any]] = {
        # Orders
        'ORDER_EXECUTED': Order,
        'TRADE_INVOICE': Order,
        'SAVINGS_PLAN_EXECUTED': SavingsPlanExec,
        'SAVINGS_PLAN_INVOICE_CREATED': SavingsPlanExec,
        'ACCOUNT_TRANSFER_INCOMING': AccountTransferIncoming,
        'SECURITIES_TRANSFER_OUTGOING': SecuritiesTransferOutgoing,
        'ssp_securities_transfer_outgoing': SecuritiesTransferOutgoing,
        'ORDER_EXPIRED': Ignore,
        'ORDER_CANCELED': Ignore,
        'YEAR_END_TAX_REPORT': Ignore,
        'PRE_DETERMINED_TAX_BASE_EARNING': Ignore,
        'REFERENCE_ACCOUNT_CHANGED': Ignore,
        'EX_POST_COST_REPORT': Ignore,
        'card_successful_verification': Ignore,
        # Payments
        'PAYMENT_INBOUND': PaymentInbound,
        'INCOMING_TRANSFER': PaymentInbound,
        'PAYMENT_INBOUND_SEPA_DIRECT_DEBIT': PaymentInboundSepaDirectDebit,
        'PAYMENT_OUTBOUND': PaymentOutbound,
        'OUTGOING_TRANSFER': PaymentOutbound,
        'INCOMING_TRANSFER_DELEGATION': PaymentInbound,
        'OUTGOING_TRANSFER_DELEGATION': PaymentOutbound,
        'CREDIT': Dividend,
        'ssp_corporate_action_invoice_cash': Dividend,
        'INTEREST_PAYOUT_CREATED': InterestPayout,
        'INTEREST_PAYOUT': InterestPayout,
        'card_successful_oct': CardOriginalCreditTransaction,
        'card_order_billed': CardOrderBilled,
        'card_refund': CardRefund,
        'card_successful_atm_withdrawal': CardWithdrawal,
        'STOCK_PERK_REFUNDED': StockPerkRefunded,
        'REPAYMENT': BondRepayment,
        # Card
        'card_successful_transaction': CardTransaction,
        'card_failed_transaction': Ignore,
        'card_failed_atm_withdrawal': Ignore,
        'card_failed_verification': Ignore,
        # Card related orders
        'benefits_spare_change_execution': RoundUp,
        'benefits_saveback_execution': SaveBack,
        # Bonds
        'COUPON_PAYMENT': CouponPayment,
        # Account
        'PUK_CREATED': Ignore,
        'CUSTOMER_CREATED': Ignore,
        'SECURITIES_ACCOUNT_CREATED': Ignore,
        'DOCUMENTS_CREATED': Ignore,
        'DOCUMENTS_ACCEPTED': Ignore,
        'DEVICE_RESET': Ignore,
        'PIN_RESET': Ignore,
        'EMAIL_VALIDATED': Ignore,
        'INPAYMENTS_SEPA_MANDATE_CREATED': Ignore,
        'QUARTERLY_REPORT': Ignore,
        'GESH_CORPORATE_ACTION': Ignore,
        'new_tr_iban': Ignore,
        'ssp_corporate_action_informative_notification': Ignore,
        'VERIFICATION_TRANSFER_ACCEPTED': Ignore,
        'MOBILE_CHANGED': Ignore,
        'STOCK_PERK_EXPIRED': Ignore,
        'AML_SOURCE_OF_WEALTH_RESPONSE_EXECUTED': Ignore,
        'MOBILE_RESET': Ignore,
        # Taxes
        'EXEMPTION_ORDER_CHANGED': Ignore,
        'EXEMPTION_ORDER_CHANGE_REQUESTED': Ignore,
        'TAX_REFUND': TaxRefund,
    }

    def convert(self, events: dict, payments_file: None|str|Path, orders_file: None|str|Path):
        processed = self.process(events)

        if payments_file:
            with open(payments_file, 'w', encoding='utf-8') as fh:
                fh.write(Payment.csv_header())
                for p in processed:
                    if isinstance(p, Payment):
                        fh.write(p.csv())

        if orders_file:
            with open(orders_file, 'w', encoding='utf-8') as fh:
                fh.write(Investment.csv_header())
                for p in processed:
                    if isinstance(p, Investment):
                        fh.write(p.csv())

    def process(self, events: dict):
        data = []
        for event in events:
            func = self.event_types.get(event['eventType'], Unknown)
            ev = func(event)
            if isinstance(ev, Unknown):
                print(f"Unknown event type {event['eventType']}")
            if not isinstance(ev, Ignore):
                data.append(func(event))
        return data


def main():
    import sys
    from pathlib import Path
    filename = sys.argv[1]
    with open(filename, 'rt', encoding='utf-8') as fh:
        events = json.load(fh)
    basedir = Path(filename).parent
    Converter.convert(events, basedir / 'payments.csv', basedir / 'orders.csv')


if __name__ == '__main__':
    main()
