# battery-historian-ng
simple replacement for battery-historian 

## how to use

generate a perfetto json file from a bugreport
```
./generate_json_from_br.sh my_br.zip
```

open `my_br.zip.json` in https://ui.perfetto.dev

Use "Set timestamp and duration format" and select UTC to have real utc date

## example

open test trace with this link
https://ui.perfetto.dev/#!/?url=https://raw.githubusercontent.com/mat-c/battery-historian-ng/refs/heads/main/tests/pixel7_android16.txt.json

## tests

```
cd tests
./check.sh
```
