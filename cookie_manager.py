import os
from typing import Dict

class CookieManager:
    def __init__(self, cookie_file: str = None):
        if cookie_file is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cookie_file = os.path.join(script_dir, 'cookie.txt')
        self.cookie_file = cookie_file

    def read_cookie(self) -> str:
        with open(self.cookie_file, 'r', encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def parse_cookie(text: str) -> Dict[str, str]:
        cookie_ = [item.strip().split('=', 1) for item in text.strip().split(';') if item]
        cookie_ = {k.strip(): v.strip() for k, v in cookie_}
        return cookie_
