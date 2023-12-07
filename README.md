# HLTV Scraper Project

### By Julian George

## Summary

This was a nearly year-long endeavor with the end goal of reliably betting upon professional Counter-Strike (CS) matches. It taught me about managing complexity and persisting through obstacles. In this README, I'll go through the different components of this project and stages of its development.

![Bet results](static/sheet.png)
![Scraping](static/scraping.gif)

## Underlying Idea

I had entertained this idea in high school, building out the scraping program and scraping all available matches before realizing I didn't have the machine learning knowledge to do anything with it. Now, with more ML understanding and more experience with complex projects, I decided to try again.

This idea was based upon a few fundamental assumptions:

1. The only source of high-quality Counter-Strike match data is through scraping HLTV.com.
   - HLTV is a CS website with stats, news, and forums, but its Cloudflare protection makes scraping hard.
   - If this is true, then scraping it all would be a barrier to entry for other people with this same idea.
2. It is possible to profit with a relatively low accuracy.
   - My goal with my machine learning model was to achieve an accuracy of 60-70%, and then make my bets in a way that would make that accuracy profitable.
   - I figured being that accurate consistently would outcompete most other bettors who lack a consistent model.
3. Successful betting strategies won't be punished by betting websites.
   - I used Thunderpick, a crypto-currency based betting site, which I assume wouldn't have the resources build a model of their own or keep track of successful bettors.

My philosophy was to try and overcome every problem I faced so long as the fundamental assumptions held up, and I only stopped this project once one of them proved wrong.

## Scraping

The first stage was scraping. I chose Node & Typescript for my scraping module, because of my familiarity with Node, and because Typescript would make the project less error-prone. I used puppeteer and cheerio for scraping, with Puppeteer imitating a browser, fetching the pages, then passing the HTML to cheerio which extracts the data from the DOM. Then, the parsed data would be sent to a MongoDB database in the cloud. Much of this was straightforwad, with the real challenge being twofold:

1. The volume of data to scrape (hundreds of thousands of matches, maps, players, and events).
2. Overcoming Cloudflare, which prevented headless scraping.

Problem 1 necessitated parallelization. Instead of running all the pages through a single puppeteer browser, I had a bank of browsers that, when available, would take and process the next page from a long queue of pages. To prevent overwhelming HLTV servers or getting blocked, I ran each browser through a different proxy. Parallelization also caused problems for the database, as it would get overwhelmed by queries. I previously would just use `await` on all DB processes, but beyond holding up the browsers, who had to wait for the database, one long/hanging DB query would lead to a backlog of other queries which would sometimes crash the database, and sometimes cause me to run out of RAM. So, I refactored the DB calls to use promises, and added a kind of middleware that passed every query to a global promise queue which would manage these parallel calls much faster and without error. This prevented crashes and allowed the browsers to operate continuously without waiting for the DB. I also ended up giving the puppeteer calls their own promise queue as well, which improved performance on their end.

Problem 2 necessitated several things. First, I used `puppeteer-extra-plugin-stealth`, a package that configured puppeteer's settings to be less detectable, but it wasn't too effective. Switching to headful browsers (ie. browsers opened with the full GUI instead of just simulated on the command line) helped, but some of my proxy's IPs would be blocked, others wouldn't overcome the Cloudflare challenges, and others would get other mysterious internet-based errors. The solution was to maintain a list of IPs longer than the amount of browsers running concurrently, and I used a 100-25 ratio for most of the project. That way, any time a browser or its IP had a problem, we could close it and open a new browser with an unused IP. At the end of every week, the provider would refresh the proxy IPs, so I never had an issue with getting blocked. This made deployment challenging though.

Code for this module can be found within the `scraping_module` directory. It includes different MongoDB `models`, `parsers` to extract those models from their associated webpages, `processors` that handle cleaning of certain string fields, and `services` that contain DB queries and model creations.

## Predicting

### Features

Once I had a full database, I started working on the machine learning component of this project. Without much experience in that field, it was a lot of trial and error, with most of the work going into processing the data.

I approached feature selection by recalling the betting intuitions of myself and others, and by watching matches and carefully asking "why did they win?"
One answer to that question came down to current form, which could be extracted from recent matches or matches earlier in the same event. Other factors were the players' experience on the match's map, their consistency, and the matchup between different player types. One important conclusion was the role of random chance deciding pivotal moments in a given match, so, by my philosophy, consistency was vital in a team being able to overcome those random occurrences.

My ultimate approach was the following:

- For each match, fetch its players previous matches over a timeframe or timeframes
- Then, iterate through those previous matches, extracting statistics about that player's performance, and about the team's performance
  - Statistics included things like rating, kill count, and performance against adversaries from the predicted match
- Categorize those statistics based on the relationship between this previous match and the predicted match
  - If this previous match was on the same map as the predicted, or if this previous match was in the same event or location
- For each category and player, aggregate the collected statistics into columns to get the final feature matrix
  - Includes getting team-wide win rates, average and stdev per-player stats, etc.

Other features were untethered to performance, including event prize pools, team rankings, player ages, and the time each team's roster had spent together.

In its current state, there are 102 features. In the past, that number was as high as 400, but performance-improving pruning, and a complete refactor of the processing file, brought that number down. Due to the various different categories (same-map, same-event, recent, long-term) and subcategories (ct-side, t-side) with statistics being described, there were a lot of features and a lot of overlap. I ended up reducing the statistics.

A full feature list can be found [here](betting_module/columns.txt)
Code for this can be found in `betting_module/processing.py` and its associated `betting_module/processing_helper.py`

### The model

For the machine learning part of this project, I used TensorFlow, which I preferred for its in-depth documentation and customizable models. I surveyed different models and figured that a Random Forest or an MLP model would be the best fit for this problem. Regression models wouldn't be optimal for our large feature size, and deep learning (CNN) models need more datapoints than I had available. After briefly trying out a Random Forest and getting unimpressive results, I switched to an MLP model (I would go back and re-test the RF every time I significantly changed the features).

Another notable change that happened in the model was the switch from a regression problem to a binary classification problem. Initially, I structured the model to provide a prediction of each team's score. My initial models to this end performed terribly. I suspect I had misconfigured them, but just looking at the abnormal nature of the data, with edge cases like ties and overtimes, I felt that regression wasn't the way to go. I switched to binary classiifcation, which provided better results from the beginning.

From there, it was largely a matter of tuning and pruning. At the beginning, I was getting just below .6 accuracy. This wasn't acceptable, because such an accuracy could be a achieved by just betting on the higher-ranked team. Running the built-in TensorFlow pruner got me to remove the raw date as a column, but didn't provide many other insights. Trial and error and a reconsideration of the problem helped me decide what columns to keep. Then, I tuned the MLP hyperparameters. The RELU activation function and the Adam optimizer didn't change, but the layer num was reduced to 6. At this point, the validation accuracy was around .64, which I found acceptable enough to move forward.

One note here was the possible impact of the match dates on the training performance. I was diligent about scrambling the data to ensure that earlier or later data wouldn't dominate training, but as I moved into testing, a random sample of matches across a decade didn't seem to represent the performance of my model on the current-time matches I would be betting on. So, to evaluate performance on more recent matches, I (somewhat crudely) built a separate matrix of the most recent matches, which I could test upon without unscrambling the rest of the data. WHen you see references to the "examine_frame", that's the more recent test data.

All of these efforts were colored by comparative inexperience with machine learning best practices, and the efficiency, quality, and functionality of the TensorFlow code is likely where I have the most room to grow.

Code for the model is within the `betting_module/learning.py` file.

## Betting

The final aspect of this project was the betting itself. My goal was for this whole project to be autonomous, so automatic betting brought this project back to scraping. Here, due to the closeness to the TensorFlow model, I wrote the betting code with Selenium. The file `betting_module/betting.py` and its dependencies go through the Thunderpick "markets", with each market corresponding to a match. If the match's maps have been decided, it calls the model using functions from `betting_module/predicting.py`, generating a prediction and placing the bets.

I mentioned before that, with such low accuracy, I would have to be specific about what bets I place. My general rules were not to bet on matches where the odds would lead to a low return, and to only bet on matches where the model had confidence in the outcome. Of course, there was a balance to be struck, because making those conditions too strict would lead to few bets being placed and a smaller sample size with more variance and less profit.

To assess the success of these conditions, I implemented a connection to Google Sheets (`betting_module/wager_sheet.py`), which would automatically log wagers, wins, losses, and help me keep a track of profitability.

## Deployment

To allow for continuous scraping and betting, I deployed to an AWS EC2 instance. After cloning this repo to that instance, SCPing the compiled node scraper, and SCPing the created model, running this huge system was as simple as giving the two `-loop.sh` scripts their own tmux window and running them. To handle the headful puppeteer clients, I used XVFB, which creates a virtualized monitor that acts as an X11 server. The EC2 instances performed surprisingly well for having to regularly open and close Chrome browsers with puppeteer and selenium, and after running it for a few weeks, I got a sense for the performance of the model and betting strategy.

## Result and Conclusion

After two weeks, most of my initial $20 investment was gone. I got a consistent -33% change per day. While investigating this, there were two possibilities for moving forward. Either I could use the results so far to make a more rigorous betting strategy, or I could experiment with new machine learning model architectures, such as RNNs. I was about to go into these possibilities, when I made a discovery that proved one of my underlying assumptions wrong.

That discovery was PandaScore, an API that readily provided the CS data that I had spent so long scraping. This removed my only advantage over other prospective betting model builders. Either I'd be competing with a volume of more-experienced model-builders, or machine-learning based betting wasn't feasible at all. Either way, even though it hurt to give up, I decided to at least put the project on pause.

Reading handfuls of papers revealed that sports betting is somewhat of an open problem within data science. Comparing my model to those of the authors, mine was unique for its huge number of features. Most other approaches limited their data to a couple dozen features: I had much more. Maybe this would be the key to success if I continued, but I found it more likely that it held back my model's performance. Additionally, other papers found ways through which the betting platforms would obstruct the successful bettors, and it seems unlikely that eSports matches are predictable enough to achieve enough accuracy to overcome those measures. Through personal observation, Counter-Strike matches seem largely random, with the most successful teams winning on small margins (in the same way that poker players do). Still, I'm optimistic that there is a way to use the burgeoning field of machine learning to predict CS matches with considerable accuracy and profitability, and I'll keep this project in mind as I improve my machine learning & data science knowledge.
