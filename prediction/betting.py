import pymongo
import os
import threading
from multiprocessing.pool import ThreadPool
from time import sleep
from datetime import datetime, timedelta
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.core.utils import ChromeType
from pyvirtualdisplay import Display

from predicting import predict_match, confirm_bet


prediction_threshold = timedelta(minutes=10)
bet_percent = 0.02
small_bet_percent = 0.01

total_balance = None


service = Service(executable_path=ChromeDriverManager().install())
options = ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument(f"user-data-dir={os.environ['CHROME_PROFILE_DIR']}")
options.add_argument(f"--profile-directory={os.environ['CHROME_PROFILE']}")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-infobars")
options.add_argument("--disable-extensions")
options.add_argument("--start-fullscreen")


def login(browser):
    browser.get("https://thunderpick.io/en/esports?login=true")
    google_ele = browser.find_element(By.CSS_SELECTOR, ".social-btn--google")
    google_ele.click()


urls_to_skip = []

bet_timeout = 10


def market_bet(prediction, market_element, bet_browser):
    home_button = market_element.find_element(
        By.CSS_SELECTOR, "button.odds-button--home-type"
    )
    home_odds = float(
        WebDriverWait(bet_browser, bet_timeout)
        .until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "button.odds-button--home-type span.odds-button__odds",
                )
            )
        )
        .text
    )
    away_button = market_element.find_element(
        By.CSS_SELECTOR, "button.odds-button--away-type"
    )
    away_odds = float(
        WebDriverWait(bet_browser, bet_timeout)
        .until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "button.odds-button--away-type span.odds-button__odds",
                )
            )
        )
        .text
    )
    total_balance = float(
        bet_browser.find_element(By.CSS_SELECTOR, "div.wallet-select__value>span").text
    )
    print(f"[{str(datetime.now())}] Current Balance: $" + str(total_balance))

    total_odds = (home_odds - 1) + (away_odds - 1)
    # counterintuitive, but for example if away odds are 12, we want new home odds to be high, not new away odds
    print("Unadjusted home/away odds", home_odds, away_odds)
    print(home_odds, home_odds - 1, total_odds)
    home_odds = (away_odds - 1) / total_odds
    away_odds = (home_odds - 1) / total_odds
    home_win = False
    if prediction[0] >= 0.4 and prediction[0] >= home_odds:
        home_win = True
        home_button.click()
        print(f"Betting home - prediction: {prediction[0]}, odds: {home_odds}")
    elif prediction[1] >= 0.4 and prediction[1] >= away_odds:
        away_button.click()
        print(f"Betting away - prediction: {prediction[1]}, odds: {away_odds}")
    else:
        print("No bet made.")
    try:
        pending_bet_input = WebDriverWait(bet_browser, 30).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.selections-list input.thp-input",
                )
            )
        )
        amount_to_bet = total_balance * (
            bet_percent
            if (
                (home_win and prediction[0] >= 0.6)
                or (not home_win and prediction[1] >= 0.6)
            )
            else small_bet_percent
        )
        amount_to_bet = max(total_balance * bet_percent, 1.1)
        pending_bet_input.send_keys(amount_to_bet)
        submit_button = bet_browser.find_element(
            By.CLASS_NAME, "bet-slip__floating-button"
        )
        submit_button.click()
        WebDriverWait(bet_browser, 10).until(
            EC.none_of(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "div.selections-list input.thp-input",
                    )
                )
            )
        )
        return True

    except Exception as e:
        print("Error", e)
        close_buttons = bet_browser.find_elements(
            By.CLASS_NAME, "selection-header__close-button"
        )
        for button in close_buttons:
            button.click()
        return False


def match_bet(predictions_dict, bet_url, bet_browser=None):
    bet_browser.get(bet_url)
    market_elements = list(
        WebDriverWait(bet_browser, 10).until(
            EC.presence_of_all_elements_located(
                (
                    By.CSS_SELECTOR,
                    "div.infinite-scroll-list > .market-accordion",
                )
            )
        )
    )
    num_maps = len(predictions_dict.items())
    market_element_dict = {}

    if num_maps == 1:
        market_elements.append(
            bet_browser.find_element(By.CLASS_NAME, "match-page__match-info-column")
        )

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

    market_bets = []

    pool = ThreadPool(processes=num_maps)

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
    print("successful_bets", successful_bets)
    return successful_bets


def make_bets(browser=None):
    sleep_length = None
    # options.add_argument("--headless")
    browser.get("https://thunderpick.io/en/esports/csgo")
    # if this doesn't exist, we aren't signed in
    try:
        user_element = browser.find_element(By.CLASS_NAME, "user-summary")
    except:
        print("Trying to log in...")
        login(browser)
        browser.implicitly_wait(15)

    now = datetime.now()
    current_year = str(datetime.now().year)

    match_sections = list(
        WebDriverWait(browser, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.match-group"))
        )
    )
    sleep(0.5)
    total_balance = float(
        browser.find_element(By.CSS_SELECTOR, "div.wallet-select__value>span").text
    )

    print(f"[{str(datetime.now())}] Current Balance: $" + str(total_balance))

    match_urls = []

    for match_section in match_sections:
        title = match_section.find_element(By.CLASS_NAME, "match-group-title").text
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
                WebDriverWait(browser, 10)
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
            WebDriverWait(browser, 10)
            .until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.main-market__home-team")
                )
            )
            .text
        )
        away_team = (
            WebDriverWait(browser, 10)
            .until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.main-market__away-team")
                )
            )
            .text
        )
        (predictions, match) = predict_match(home_team, away_team)
        # if this match isnt in the database or it has been fully bet on, skip
        if match == None or len(match["betted"]) == match["numMaps"]:
            urls_to_skip.append(bet_url)
            continue
        browser.get("https://www.hltv.org" + match["matchUrl"])
        map_names = list(
            map(
                lambda map_ele: map_ele.text,
                browser.find_elements(
                    By.CSS_SELECTOR, "div.map-name-holder > div.mapname"
                ),
            ),
        )
        market_prediction_dict = {}
        if len(map_names) == 1:
            market_prediction_dict["Match"] = predictions[map_names[0]]
        else:
            for i in range(len(map_names)):
                market_prediction_dict[f"Map {i+1} Winner"] = predictions[map_names[i]]

        # ensures that already betted markets aren't betted again
        market_prediction_dict = {
            k: v
            for k, v in market_prediction_dict.items()
            if not k in match["betted"] or not match["betted"][k]
        }
        # map_threads.append(
        #     map_pool.apply_async(match_bet, (market_prediction_dict, bet_url)).get()
        # )
        betted_markets = match_bet(market_prediction_dict, bet_url, browser)
        if False in betted_markets.values():
            sleep_length = 30
        confirm_bet(match["hltvId"], betted_markets)

    # for map_thread in map_threads:
    #     betted_markets = map_thread.get()
    #     confirm_bet(match["hltvId"], betted_markets)

    # browser.close()
    return sleep_length


browser = Chrome(service=service, options=options)
while True:
    sleep_length = 60 * 30
    try:
        # this min makes sure that new betting opportunities are caught if they are added before the next match
        sleep_length = min(make_bets(browser), sleep_length)
    except Exception as e:
        sleep_length = 60
        print("Error while betting", e)
    print("Sleeping until", str(datetime.now() + timedelta(seconds=sleep_length)))
    sleep(sleep_length)
