# battery-historian-ng
simple replacement for battery-historian 

## how to use

generate a perfetto json file from a bugreport
```
./generate_json_from_br.sh my_br.zip
```

open `my_br.zip.json` in https://ui.perfetto.dev

## example

open tests/pixel7\_android16.txt.json

## tests

```
cd tests
./check.sh
```
