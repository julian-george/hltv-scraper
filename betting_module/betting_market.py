import traceback
from time import sleep
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

from betting_helper import generic_wait, medium_wait, long_wait, balance_check

bet_timeout = 10

confident_threshold = 0.65
underdog_threshold = 0.4
site_odd_threshold = 0.02

bet_percent = 0.05
small_bet_percent = 0.01

min_bet_amount = 1.1
max_bet_amount = 2000


def close_bets(browser):
    close_buttons = browser.find_elements(
        By.CLASS_NAME, "selection-header__close-button"
    )
    for button in close_buttons:
        button.click()


# minimum value for our model's prediction if we want to bet
to_bet_threshold = 0.55


def weighted_prediction(prediction):
    # threshold_distance = confident_threshold - underdog_threshold
    # weight = ((-1 * min(prediction - confident_threshold, 0)) / threshold_distance) + 1
    # return prediction / weight
    if prediction < to_bet_threshold:
        return 0
    return prediction


def market_bet(prediction, market_element, browser):
    page_home_odds = None
    page_away_odds = None
    total_balance = None
    close_bets(browser)
    # print(market_element.get_attribute("innerHTML"))
    try:
        home_button = market_element.find_element(
            By.CSS_SELECTOR, "button.odds-button--home-type"
        )

        away_button = market_element.find_element(
            By.CSS_SELECTOR, "button.odds-button--away-type"
        )

        page_home_odds = float(
            generic_wait(browser)
            .until(
                lambda _: home_button.find_element(
                    By.CSS_SELECTOR, "span.odds-button__odds"
                )
            )
            .text
        )
        page_away_odds = float(
            generic_wait(browser)
            .until(
                lambda _: away_button.find_element(
                    By.CSS_SELECTOR, "span.odds-button__odds"
                )
            )
            .text
        )
        generic_wait(browser).until(balance_check)
        # this waits for the stupid aniamtion to finish
        sleep(0.5)
        total_balance = float(
            browser.find_element(By.CSS_SELECTOR, "div.wallet-select__value>span").text
        )
        print(f"[{str(datetime.now())}] Current Balance: $" + str(total_balance))
    except Exception as e:
        print("Market Locked")
        traceback.format_exc()
        return None
    total_odds = round((page_home_odds - 1) + (page_away_odds - 1), 3)
    # counterintuitive, but for example if away odds are 12, we want new home odds to be high, not new away odds
    home_odds = round((page_away_odds - 1) / total_odds, 3)
    away_odds = round((page_home_odds - 1) / total_odds, 3)
    # TODO: what is the point of this variable?
    home_win = False
    betted_odds = away_odds
    # remember, prediction[1] is actually the chances that home will win!
    if (
        prediction[1] >= underdog_threshold
        and weighted_prediction(prediction[1]) >= home_odds
        and home_odds > site_odd_threshold
    ):
        home_win = True
        betted_odds = home_odds
        home_button.click()
        print(
            f"Betting home - prediction: {prediction[1]}, odds: {home_odds}, unadjusted {page_home_odds}"
        )
    elif (
        prediction[0] >= underdog_threshold
        and weighted_prediction(prediction[0]) >= away_odds
        and away_odds > site_odd_threshold
    ):
        away_button.click()
        print(
            f"Betting away - prediction: {prediction[0]}, odds: {away_odds}, unadjusted {page_away_odds}"
        )
    else:
        print(f"No bet made. Prediction: {prediction}, odds: {[home_odds,away_odds]}")
        return {
            "prediction": prediction,
            "odds": [home_odds, away_odds],
            "betted_amount": 0,
            "betted_odds": None,
            # "try_num": 0,
        }
    try:
        pending_bet_input = long_wait(browser).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.selections-list input.thp-input",
                )
            )
        )
        amount_to_bet = total_balance * bet_percent
        # bets either the calculated percentage amount or the min/max
        amount_to_bet = min(
            max(total_balance * bet_percent, min_bet_amount), max_bet_amount
        )
        pending_bet_input.send_keys(amount_to_bet)
        submit_button = browser.find_element(By.CLASS_NAME, "bet-slip__floating-button")
        submit_button.click()
        sleep(1)
        medium_wait(browser).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.bet-slip-info--bet-accepted",
                )
            )
        )
        close_bets(browser)

        return {
            "prediction": prediction,
            "odds": [home_odds, away_odds],
            "betted_amount": amount_to_bet,
            "betted_odds": betted_odds,
        }

    except Exception as e:
        print("Error while confirming bet")
        print(traceback.format_exc())
        close_bets(browser)
        return None
