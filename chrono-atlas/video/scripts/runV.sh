#!/bin/bash
cd ~/chrome-for-testing/rt
(cd site && setsid python3 ../srv.py >/dev/null 2>&1 </dev/null &)
sleep 1
export CHROMEBIN=$HOME/chrome-for-testing/chrome-linux64/chrome
export GLARGS="--use-angle=vulkan --enable-features=Vulkan --disable-vulkan-surface"
echo start $(date -Is)
DSF=2 node r/render2g.mjs 2700 outV 0 2700 video_V5.html 540 960
echo end $(date -Is)
fuser -k 18765/tcp >/dev/null 2>&1
