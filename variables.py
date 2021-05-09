import os

dev = False

main_twitter_login_file = "logins/twitter_login.json"
dev_twitter_login_file = "logins/test_twitter_login.json"
main_s3_config_key = "config/twitter_bot_config.json"
dev_s3_config_key = "config/twitter_bot_config_test.json"
main_process_tweet_lambda_func = "WD_Twitter_ProcessTweet"
dev_process_tweet_lambda_func = "TEST_WD_Twitter_ProcessTweet"
if dev:
    twitter_login_file = dev_twitter_login_file
    s3_config_key = dev_s3_config_key
    process_tweet_lambda_func = dev_process_tweet_lambda_func
else:
    twitter_login_file = main_twitter_login_file
    s3_config_key = main_s3_config_key
    process_tweet_lambda_func = main_process_tweet_lambda_func



LAST_TWEET_ID_TAG_KEY = "LAST_STATUS_ID"
s3_bucket = "faldetector"
s3_images_dir = "images"
lambda_face_detect_func = "FaceDetector"
lambda_warp_heatmap_func = "Warp-Heatmap-Generator"
instagram_accounts_key = "config/instagram_accounts.json"
twitter_accounts_key = "config/twitter_accounts.json"
instagram_login_file = "logins/instagram_login.json"
tweet_queue_key = "config/tweet_queue.txt"
tweet_queue_done_key = "{}_done{}".format(*os.path.splitext(tweet_queue_key))
