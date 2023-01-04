sudo apt-get update
sudo apt-get install nano xauth xvfb x11-xkb-utils xfonts-100dpi xfonts-75dpi xfonts-scalable xfonts-cyrillic xinput x11-apps npm libasound2 libgbm1 libgm2-0
git clone https://github.com/julian-george/hltv-scraper && cd hltv-scraper && npm i && npm run build && npm start
xvfb-run -e --server-args="-screen 0 1024x768x24 -ac -nolisten tcp -nolisten unix" ico -facess