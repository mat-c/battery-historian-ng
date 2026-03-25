#! /bin/sh
set -e
set -x

if [ ! -f "$1" ]
then
        echo "missing BR as arg"
        exit 1
fi

TEMP=$(mktemp -d)

unzip "$1" -d $TEMP "bugreport*.txt"


#grep -a "^9,h" $@
grep -a "^9," $TEMP/bugreport*.txt


rm -rf $TEMP
