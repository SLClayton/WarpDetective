# @WarpDetective

This project uses the trained AI from a research project called "Detecting Photoshopped Faces by Scripting Photosho" by Wang, Sheng-Yu and Wang, Oliver and Owens, Andrew and Zhang, Richard and Efros, Alexei A. Their project page can be found at the url linked here: https://peterwang512.github.io/FALdetector/


WarpDetective is a twitter bot which can when requested by any twitter user, take a social media post, extract a chosen image and run it through a trained AI to see where it may have been manipulated. It will then tweet back its results to the original request tweet.

This project is made up of 2 distinct phases.
1. Port over all necessary Machine Learning models/Face detection onto a serveles configuration on AWS lambda so it can be run on standby 24/7 without incurring any cost unless it is needed. This was a lot more dfficult than originally thought.
2. Create the bot that can navigate twitter mentions/media/replies and correctly apply the required request to the ported processess and correctly reply with the response. This is the code that this repo contains.

<p align="middle">
  <img src="https://pbs.twimg.com/media/EYttjUXWoAEkVwN?format=jpg&name=large" width="450">
  <img src="https://pbs.twimg.com/media/EYttj2MXkAEdOmQ?format=jpg&name=large" width="450">
</p>
