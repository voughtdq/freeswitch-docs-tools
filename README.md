# freeswitch-docs-tools

Tools to aid editing FreeSWITCHⓇ documentation.

## find_variables.py

A script to assist searching the [FreeSWITCHⓇ repository](https://github.com/signalwire/freeswitch)
for variables. Known to work with Python 3.10.12.

### Usage

```
# clone the repo
git clone --branch v1.10.11 https://github.com/signalwire/freeswitch freeswitch
# run the script
python find_variables.py --base freeswitch --out variables.ugly.json
# prettify the output and save it in data/variables.json
python -m json.tool variables.ugly.json > data/variables.json
```
