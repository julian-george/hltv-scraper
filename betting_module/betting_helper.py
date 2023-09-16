import dateparser
from datetime import datetime, timedelta
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By


ignored_exceptions = [StaleElementReferenceException, AssertionError]


def balance_check(browser):
    # this checks to see if the currency is correctly USD
    browser.find_element(By.CSS_SELECTOR, "i.ft-currency-usd")
    temp_balance = browser.find_element(
        By.CSS_SELECTOR, "div.wallet-select__value>span"
    ).text.replace(",", "")
    temp_balance = float(temp_balance)
    if temp_balance > 0.0:
        return temp_balance
    else:
        raise StaleElementReferenceException


def generic_wait(browser):
    return WebDriverWait(browser, 10, ignored_exceptions=ignored_exceptions)


def medium_wait(browser):
    return WebDriverWait(browser, 20, ignored_exceptions=ignored_exceptions)


def long_wait(browser):
    return WebDriverWait(browser, 30, ignored_exceptions=ignored_exceptions)


prediction_threshold = timedelta(minutes=10)


def date_past_threshold(date):
    now = datetime.now()
    if date == None:
        date = now
    parsed_date = dateparser.parse(date)
    if parsed_date - now > prediction_threshold:
        return True
    else:
        return False
