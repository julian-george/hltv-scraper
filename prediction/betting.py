import pymongo
import os
import threading
import traceback
from multiprocessing.pool import ThreadPool
from time import sleep
from datetime import datetime, timedelta
from webdriver_manager.chrome import ChromeDriverManager
from undetected_chromedriver import Chrome, ChromeOptions

# from selenium.webdriver import Chrome,ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.core.utils import ChromeType

from predicting import (
    predict_match,
    confirm_bet,
    set_maps,
    get_unplayed_match_by_team_names,
)


ignored_exceptions = [StaleElementReferenceException, AssertionError]

prediction_threshold = timedelta(minutes=10)
bet_percent = 0.05
small_bet_percent = 0.01

min_bet_amount = 1.1
max_bet_amount = 2000

total_balance = None


service = Service(
    executable_path=ChromeDriverManager(version="114.0.5735.90").install()
)
# service = None
options = ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument(f"user-data-dir={os.environ['CHROME_PROFILE_DIR']}")
options.add_argument(f"--profile-directory={os.environ['CHROME_PROFILE']}")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-infobars")
options.add_argument("--disable-extensions")
options.add_argument("--disable-gpu")
options.add_argument("--start-fullscreen")


def generic_wait(browser):
    return WebDriverWait(browser, 10, ignored_exceptions=ignored_exceptions)


def login(browser):
    browser.get("https://thunderpick.io/en/esports?login=true")
    google_ele = browser.find_element(By.CSS_SELECTOR, ".social-btn--google")
    google_ele.click()
    sleep(1)
    WebDriverWait(browser, 30, ignored_exceptions=ignored_exceptions).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.thp-info-image__icon-container--success")
        )
    )
    generic_wait(browser).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.match-group"))
    )


urls_to_skip = []

bet_timeout = 10


def close_bets(browser):
    close_buttons = browser.find_elements(
        By.CLASS_NAME, "selection-header__close-button"
    )
    for button in close_buttons:
        button.click()


def balance_check(browser):
    correct_currency = browser.find_element(By.CSS_SELECTOR, "i.ft-currency-usd")
    temp_balance = browser.find_element(
        By.CSS_SELECTOR, "div.wallet-select__value>span"
    ).text.replace(",", "")
    temp_balance = float(temp_balance)
    if temp_balance > 0.0:
        return temp_balance
    else:
        raise StaleElementReferenceException


confident_threshold = 0.65
underdog_threshold = 0.4
site_odd_threshold = 0.02


def weighted_prediction(prediction):
    # threshold_distance = confident_threshold - underdog_threshold
    # weight = ((-1 * min(prediction - confident_threshold, 0)) / threshold_distance) + 1
    # return prediction / weight
    return prediction


def market_bet(prediction, market_element, bet_browser):
    page_home_odds = None
    page_away_odds = None
    total_balance = None
    close_bets(bet_browser)
    # print(market_element.get_attribute("innerHTML"))
    try:
        odds_wait = WebDriverWait(
            browser, bet_timeout, ignored_exceptions=ignored_exceptions
        )

        home_button = market_element.find_element(
            By.CSS_SELECTOR, "button.odds-button--home-type"
        )

        away_button = market_element.find_element(
            By.CSS_SELECTOR, "button.odds-button--away-type"
        )

        page_home_odds = float(
            odds_wait.until(
                lambda _: home_button.find_element(
                    By.CSS_SELECTOR, "span.odds-button__odds"
                )
            ).text
        )
        page_away_odds = float(
            odds_wait.until(
                lambda _: away_button.find_element(
                    By.CSS_SELECTOR, "span.odds-button__odds"
                )
            ).text
        )
        generic_wait(bet_browser).until(balance_check)
        # this waits for the stupid aniamtion to finish
        sleep(0.5)
        total_balance = float(
            bet_browser.find_element(
                By.CSS_SELECTOR, "div.wallet-select__value>span"
            ).text
        )
        print(f"[{str(datetime.now())}] Current Balance: $" + str(total_balance))
    except Exception:
        print("Market locked")
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
        and away_odds > site_odd_threshold
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
        }
    try:
        pending_bet_input = WebDriverWait(
            bet_browser, 30, ignored_exceptions=ignored_exceptions
        ).until(
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
        submit_button = bet_browser.find_element(
            By.CLASS_NAME, "bet-slip__floating-button"
        )
        submit_button.click()
        sleep(1)
        WebDriverWait(bet_browser, 20, ignored_exceptions=ignored_exceptions).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.bet-slip-info--bet-accepted",
                )
            )
        )
        close_bets(bet_browser)

        return {
            "prediction": prediction,
            "odds": [home_odds, away_odds],
            "betted_amount": amount_to_bet,
            "betted_odds": betted_odds,
        }

    except Exception as e:
        print("Error while confirming bet")
        print(traceback.format_exc())
        close_bets(bet_browser)
        return None


def match_bet(predictions_dict, bet_url, num_maps, bet_browser=None):
    bet_browser.get(bet_url)
    market_elements = []
    if num_maps == 1:
        market_elements.append(
            generic_wait(bet_browser).until(
                EC.presence_of_element_located((By.CLASS_NAME, "main-market"))
            )
        )
    else:
        try:
            market_elements = list(
                generic_wait(bet_browser).until(
                    EC.presence_of_all_elements_located(
                        (
                            By.CSS_SELECTOR,
                            "div.infinite-scroll-list > .market-accordion",
                        )
                    )
                )
            )
            # print("market elements", market_elements)
        except Exception:
            print("No market elements")
            # return {}
    market_element_dict = {}
    for market_element in market_elements:
        market_title = "Match"
        try:
            market_title = market_element.find_element(
                By.CLASS_NAME, "market-accordion__market-name"
            ).text
        except:
            pass
        if market_title in predictions_dict.keys():
            market_element_dict[market_title] = market_element

    successful_bets = {}
    for title, element in market_element_dict.items():
        # market_bets.append(
        #     threading.Thread(
        #         market_bet,
        #         args=(predictions_dict[title], element, bet_browser),
        #         daemon=True,
        #     )
        # )
        # market_bets.append(
        #     (
        #         title,
        #         pool.apply_async(
        #             market_bet, (predictions_dict[title], element, bet_browser)
        #         ),
        #     )
        # )
        print("Betting", title, bet_url, predictions_dict)
        sleep(0.5)
        successful_bets[title] = market_bet(
            predictions_dict[title], element, bet_browser
        )

    # wait for all bet threads to conclude before continuing
    # for bet_thread_tuple in market_bets:
    #     bet_title = bet_thread_tuple[0]
    #     bet_success = bet_thread_tuple[1].get()
    #     if bet_success:
    #         successful_bets.append(bet_title)

    # bet_browser.close()
    print("Successful Bets", successful_bets)
    return successful_bets


def make_bets(browser=None):
    sleep_length = None
    # options.add_argument("--headless")
    browser.get("https://thunderpick.io/en/esports/csgo")
    # if this doesn't exist, we aren't signed in
    try:
        user_element = generic_wait(browser).until(
            EC.presence_of_element_located((By.CLASS_NAME, "user-summary"))
        )
    except:
        print("Trying to log in...")
        login(browser)
        browser.get("https://thunderpick.io/en/esports/csgo")

    now = datetime.now()
    current_year = str(datetime.now().year)

    match_sections = list(
        generic_wait(browser).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.match-group"))
        )
    )
    generic_wait(browser).until(balance_check)
    sleep(0.5)
    total_balance = float(
        browser.find_element(By.CSS_SELECTOR, "div.wallet-select__value>span").text
    )

    print(f"[{str(datetime.now())}] Current Balance: $" + str(total_balance))

    match_urls = []

    for match_section in match_sections:
        title = (
            generic_wait(browser)
            .until(
                lambda _: match_section.find_element(By.CLASS_NAME, "match-group-title")
            )
            .text
        )
        if title != "Featured":
            match_urls += list(
                map(
                    lambda link: link.get_attribute("href"),
                    match_section.find_elements(
                        By.CSS_SELECTOR, "a.match-row__total-markets"
                    ),
                )
            )

    match_urls = [url for url in match_urls if not url in urls_to_skip]

    map_threads = []
    map_pool = ThreadPool()

    for bet_url in match_urls:
        browser.get(bet_url)
        match_date = None
        try:
            match_date = (
                generic_wait(browser)
                .until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "match-header__date")
                    )
                )
                .text
            )
            match_date = datetime.strptime(
                current_year + " " + match_date, "%Y %B %d, %H:%M"
            )
        except:
            match_date = now
        if match_date - now > prediction_threshold:
            print("Past threshold, ending until bet at", bet_url)
            if sleep_length == None:
                sleep_length = (match_date - now).total_seconds() - 600
            # browser.close()
            return sleep_length
        home_team = (
            generic_wait(browser)
            .until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.main-market__home-team")
                )
            )
            .text
        )
        away_team = (
            generic_wait(browser)
            .until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.main-market__away-team")
                )
            )
            .text
        )
        (match, same_order) = get_unplayed_match_by_team_names(
            home_team, away_team, datetime.now()
        )
        # if this match isnt in the database or it has been fully bet on, skip
        if match == None:
            print("No match found for", home_team, away_team)
            urls_to_skip.append(bet_url)
            continue
        elif (
            len(
                [
                    map_betted
                    for map_betted in match["betted"].values()
                    if map_betted != None
                ]
            )
            == match["numMaps"]
        ):
            print("All maps betted for", home_team, away_team)
            urls_to_skip.append(bet_url)
            continue
        map_infos = match.get("mapInfos", [])
        if len(map_infos) != match["numMaps"]:
            # do this for edge case that only one map is TBA to prevent adding duplicate maps
            map_infos = []
            browser.get("https://www.hltv.org" + match["matchUrl"])
            print("Page loaded", match["matchUrl"])
            generic_wait(browser).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.mapholder"))
            )
            mapholders = browser.find_elements(By.CSS_SELECTOR, "div.mapholder")
            print(len(mapholders), "mapholders found")
            for i, holder in enumerate(mapholders):
                map_name = holder.find_element(By.CSS_SELECTOR, "div.mapname").text
                picked_by = None
                left_picked = (
                    len(holder.find_elements(By.CSS_SELECTOR, ".results-left.pick"))
                    == 1
                )
                right_picked = (
                    len(holder.find_elements(By.CSS_SELECTOR, ".results-right.pick"))
                    == 1
                )
                if left_picked:
                    picked_by = "teamOne"
                elif right_picked:
                    picked_by = "teamTwo"
                map_info = {"map_name": map_name, "picked_by": picked_by, "map_num": i}
                print("New map info", map_info)
                map_infos.append(map_info)

            set_maps(
                match["hltvId"],
                [map_info for map_info in map_infos if map_info["map_name"] != "TBA"],
            )
        map_names = list(map(lambda info: info["map_name"], map_infos))
        market_prediction_dict = {}
        if "TBA" in map_names:
            print("Maps still TBA")
            sleep_length = 30
            continue
        predictions = predict_match(match, map_infos, same_order)
        if len(map_names) == 1:
            market_prediction_dict["Match"] = predictions[map_names[0]]
        else:
            for i in range(len(map_names)):
                market_name = f"Map {i+1} Winner"
                if map_names[i] == "Default":
                    confirm_bet(match["hltvId"], {market_name: True})
                if map_names[i] in predictions:
                    market_prediction_dict[market_name] = predictions[map_names[i]]

        # ensures that already betted markets aren't betted again
        market_prediction_dict = {
            k: v
            for k, v in market_prediction_dict.items()
            if not k in match["betted"] or not match["betted"][k]
        }
        # map_threads.append(
        #     map_pool.apply_async(match_bet, (market_prediction_dict, bet_url)).get()
        # )
        print("Trying to bet on", match["title"])
        betted_markets = match_bet(
            market_prediction_dict, bet_url, match["numMaps"], browser
        )
        if None in betted_markets.values():
            sleep_length = 30
        confirm_bet(match["hltvId"], betted_markets)

    # for map_thread in map_threads:
    #     betted_markets = map_thread.get()
    #     confirm_bet(match["hltvId"], betted_markets)

    browser.close()
    return sleep_length


browser = Chrome(options=options)
while True:
    sleep_length = 60 * 30
    try:
        # this min makes sure that new betting opportunities are caught if they are added before the next match
        sleep_length = min(make_bets(browser), sleep_length)
    except Exception as e:
        sleep_length = 60
        print("Error while betting", e)
        print(traceback.format_exc())
    print("Sleeping until", str(datetime.now() + timedelta(seconds=sleep_length)))
    sleep(sleep_length)
