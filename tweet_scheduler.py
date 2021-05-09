import json
import random
import traceback
from pprint import pprint as pp

from tools import *
from variables import *

import twitter
from twitter.twitter_utils import enf_type
from twitter.error import TwitterError

def getTwitterApi(login):

    # If a string is passed, then its filename, get the JSON it refers to.
    if isinstance(login, str):
        with open(login, "r", encoding="utf-8") as f:
            login = json.load(f)


    # Login to twitter
    api = twitter.Api(consumer_key=login["consumer_key"],
                      consumer_secret=login["consumer_secret"],
                      access_token_key=login["access_token_key"],
                      access_token_secret=login["access_token_secret"])

    return api

def tweetString(tweet):
    s = "{} {} @{}: {}".format(
        datetime.utcfromtimestamp(tweet.created_at_in_seconds).strftime("%Y-%m-%d %H-%M-%S"),
        tweet.id,
        tweet.user.screen_name,
        tweet.text)
    return s


def lambda_handler_processor(event, context):
    # Tweets the next tweet in the queue from a random test twitter account

    try:

        # Get the queue and the done queue from s3
        print("Downloading queues from s3")
        twitter_queue = getListFromS3(s3_bucket, tweet_queue_key)
        if tweet_queue_key is None or len(tweet_queue_key) == 0:
            return {"statusCode": 200, "body": "Queue doesn't exist or is empty."}

        twitter_queue_done = getListFromS3(s3_bucket, tweet_queue_done_key)
        if twitter_queue_done is None:
            twitter_queue_done = []

        # Get the dev twitter accounts and pick a random one to login to twitter with
        print("Getting twitter login details from s3")
        twitter_accounts = getJSONFroms3(s3_bucket, twitter_accounts_key)
        username = random.choice(list(twitter_accounts.keys()))
        twitter_api = getTwitterApi(twitter_accounts[username])
        print("logged in as @{}".format(twitter_api.VerifyCredentials().screen_name))

        # Get next tweet in queue and tweet it
        next_tweet_text = twitter_queue[0]
        print("Chosen next tweet text: '{}'".format(next_tweet_text))
        tweet = twitter_api.PostUpdate(status=next_tweet_text)
        print(tweetString(tweet))

        # Update lists
        print("Updating queue lists.")
        twitter_queue_done.insert(0, twitter_queue.pop(0))
        saveListToS3(twitter_queue, s3_bucket, tweet_queue_key)
        saveListToS3(twitter_queue_done, s3_bucket, tweet_queue_done_key)

        return {"statusCode": 200,
                "body": "Tweet processed successfully",
                "tweet": tweetString(tweet)}

    except Exception as e:
        traceback.print_exc()
        print("Unexpected Exception: {}".format(e))
        return {"statusCode": 500,
                "body": str(e)}



if __name__ == '__main__':
    lambda_handler_processor(None, None)