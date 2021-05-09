import json
from datetime import datetime, timedelta
import time

from tools import *

from variables import *
import twitter_tools
from TweetProcess import TweetProcess



def process_mentions(since_id=None):

    # Initialize twitter api
    twitter_api = twitter_tools.getTwitterApi(twitter_login_file)
    credentials = twitter_api.VerifyCredentials()
    our_handle = credentials.screen_name

    now = datetime.utcnow()
    print("Checking mentions{} at {}".format("" if since_id is None else " after {}".format(since_id), now))

    lookback_limit = now - timedelta(minutes=5)
    print("lookbacklimit:", lookback_limit)


    mentions = twitter_api.GetMentions(count=200, since_id=since_id)
    mentions = [m for m in mentions if datetime.utcfromtimestamp(m.created_at_in_seconds) > lookback_limit]
    mentions.sort(key=lambda k: k.created_at_in_seconds)

    for tweet in mentions:
        since_id = tweet.id if since_id is None else max(tweet.id, since_id)

        print("🠟🠟🠟🠟🠟🠟🠟🠟🠟🠟-NEW_MENTION-🠟🠟🠟🠟🠟🠟🠟🠟🠟🠟")
        try:
            print("For tweet {}".format(twitter_tools.tweetString(tweet)))

            if twitter_tools.tweet_mentions(tweet, our_handle):
                print("Sending tweet to be processed")
                lamd.invoke(FunctionName=process_tweet_lambda_func,
                            InvocationType="Event",
                            LogType="Tail",
                            Payload=json.dumps({"tweet_id": tweet.id}))
            else:
                print("Tweet doesn't need processing.")

        except Exception as e:
            print("Exception processing tweet {} - {}".format(tweet.id, e))

        print("🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝")


    if len(mentions) == 0:
        print("NO MENTIONS found since last check.")


    return since_id



def lambda_handler_preprocessor(event, context):

    # Collect the last tweet id checked in previous func if there is one
    try:
        since_id = int(getTag(context, LAST_TWEET_ID_TAG_KEY))
    except TypeError:
        since_id = None

    # Process mentions and getting last processed tweet id
    new_since_id = process_mentions(since_id=since_id)

    # Save the ID of the last tweet checked for next call of function
    if new_since_id is not None and (since_id is None or new_since_id > since_id):
        saveTag(context, LAST_TWEET_ID_TAG_KEY, str(new_since_id))
        print("Saved tag {} as {}".format(LAST_TWEET_ID_TAG_KEY, new_since_id))

    return {
        'statusCode': 200,
        'body': "Tweets processed successfully. Last tweet processed: {}".format(since_id)
    }



def preprocessor_test():
    class Context:
        def __init__(self):
            arn = "arn:aws:lambda:us-east-1:542157534763:function:TEST_WD-Twitter-PreProcessor"
            self.invoked_function_arn = arn

    context = Context()

    while True:
        lambda_handler_preprocessor(None, context)
        time.sleep(30)






def lambda_handler_processor(event, context):
    print("🠟🠟🠟🠟🠟🠟🠟🠟🠟🠟-NEW-TWEET-🠟🠟🠟🠟🠟🠟🠟🠟🠟🠟")

    try:
        tweet_id = event["tweet_id"]
    except KeyError:
        return {
            "statusCode": 404,
            "error": "No tweet_id given in input"
        }



    config = getJSONFroms3(s3_bucket, s3_config_key)
    try:
        force = event["force"]
        assert isinstance(force, bool)
    except KeyError:
        force = False

    tweet_process = TweetProcess(twitter_login_file, config, tweet_id)
    tweet_process.process_tweet(force)


    print("🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝🠝")

    if tweet_process.reply_tweet is None:
        return {
            "statusCode": 200,
            "body": "No reply tweet was sent.",
            "input_tweet": twitter_tools.statusURL(tweet_id)
        }

    return {
        "statusCode": 200,
        "body": "Tweet processed successfully",
        "input_tweet": twitter_tools.statusURL(tweet_id),
        "reply_tweet": twitter_tools.statusURL(tweet_process.reply_tweet.id)
    }


def process_tweet_test(tweet_id, force=False):
    event = {"tweet_id": tweet_id, "force": force}
    response = lambda_handler_processor(event, None)
    pp(response)




if __name__ == '__main__':
    preprocessor_test()