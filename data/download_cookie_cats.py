"""Download the public Cookie Cats A/B-test dataset (90,189 players).

Original source: Kaggle / DataCamp "Mobile Games A/B Testing with Cookie Cats".
Mirror used here: github.com/robguilarr/ab_testing_cookie_cats
"""
from pathlib import Path
from urllib.request import urlretrieve

URL = "https://raw.githubusercontent.com/robguilarr/ab_testing_cookie_cats/main/datasets/cookie_cats.csv"
out = Path(__file__).parent / "cookie_cats.csv"
urlretrieve(URL, out)
print(f"saved {out}")
