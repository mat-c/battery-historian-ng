#! /bin/sh

set -e

if [ $# -lt 1 ]
then
        echo "$0 input_br.zip [out.json]"
        exit 1
fi
FILE=$1

if [ $# -lt 2 ]
then
        OUT=$FILE.json
else
        OUT=$2
fi

./extract_from_br.sh $FILE > $OUT.bat
./parse.py < $OUT.bat > $OUT
rm $OUT.bat

echo "json generated in $OUT"
