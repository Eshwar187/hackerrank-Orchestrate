import os
import pandas as pd
import numpy as np
from datetime import datetime

IMAGE_AMOUNTS = {
    'event_253': 4365000.0,
    'event_1442': 100000.0,
    'event_1545': 41272.0,
    'event_1700': 2854.0,
    'event_1786': 822.05,
    'event_3051': 1995.0,
    'event_3231': 8528.0,
    'event_4535': 15339.0,
    'event_5170': 723.0,
    'event_6033': 79679.26,
    'event_6859': 3650.0,
    'event_7307': 33.50,
    'event_7941': 2298.0,
    'event_9421': 4543.0,
    'event_9806': 9968.0,
    'event_10521': 393.22,
}

class DataLoader:
    def __init__(self, data_dir='dataset'):
        self.data_dir = data_dir
        self.profiles = pd.read_csv(os.path.join(data_dir, 'financial_profiles.csv'))
        self.events = pd.read_csv(os.path.join(data_dir, 'financial_events.csv'))
        self.exchange_rates = pd.read_csv(os.path.join(data_dir, 'exchange_rates.csv'))
        self.payment_options = pd.read_csv(os.path.join(data_dir, 'request_payment_options.csv'))
        self.messages = pd.read_csv(os.path.join(data_dir, 'messages.csv'))
        self.requests = pd.read_csv(os.path.join(data_dir, 'requests.csv'))
        self.sample_requests = pd.read_csv(os.path.join(data_dir, 'sample_requests.csv'))
        self._apply_image_amounts()
        self._prepare_exchange_rates()

    def _apply_image_amounts(self):
        for event_id, amt in IMAGE_AMOUNTS.items():
            mask = self.events['event_id'] == event_id
            self.events.loc[mask, 'amount'] = amt

    def _prepare_exchange_rates(self):
        self.rate_map = {}
        for _, r in self.exchange_rates.iterrows():
            key = (r['rate_date'], r['from_currency'], r['to_currency'])
            self.rate_map[key] = float(r['rate'])

    def get_exchange_rate(self, date_str, from_curr, to_curr):
        if from_curr == to_curr:
            return 1.0
        if (date_str, from_curr, to_curr) in self.rate_map:
            return self.rate_map[(date_str, from_curr, to_curr)]
        # Match closest date
        matching = [
            (d, r) for (d, fc, tc), r in self.rate_map.items()
            if fc == from_curr and tc == to_curr
        ]
        if matching:
            matching.sort(key=lambda x: abs((datetime.strptime(x[0], '%Y-%m-%d') - datetime.strptime(date_str, '%Y-%m-%d')).total_seconds()))
            return matching[0][1]
        return 1.0

if __name__ == '__main__':
    dl = DataLoader()
    print('DataLoader initialized successfully.')
    print('Events shape:', dl.events.shape)
    print('Missing amounts in events:', dl.events['amount'].isna().sum())
