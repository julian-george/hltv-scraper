from time import sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from betting_helper import generic_wait
from betting_market import market_bet


def match_bet(predictions_dict, bet_url, num_maps, browser=None):
    print("match_bet")
    browser.get(bet_url)
    print("GET", bet_url)
    market_elements = []
    if num_maps == 1:
        market_elements.append(
            generic_wait(browser).until(
                EC.presence_of_element_located((By.CLASS_NAME, "main-market"))
            )
        )
    else:
        try:
            market_elements = list(
                generic_wait(browser).until(
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
    print("Market elements found")
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
        print("Betting", title, bet_url, predictions_dict)
        sleep(0.5)
        successful_bets[title] = market_bet(predictions_dict[title], element, browser)

    # browser.close()
    print("Successful Bets", successful_bets)
    return successful_bets
