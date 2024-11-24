#!/bin/bash

function random_string {
    head -c 20 /dev/urandom | base32
}

# Create a CSV file
NAME="$(random_string).csv"

echo "Name,Secret" > $NAME
echo "example1,lNdKVZUaMmjr3o4" >> $NAME
echo "example2,HcRw2lWAqT205jo" >> $NAME

for i in {1..10} ; do
    echo "$(random_string),$(random_string)" >> $NAME
    if [ $i -eq 5 ]; then
        echo "$(random_string),$FLAG" >> $NAME
    fi
done

# Upload to S3
curl -X POST http://$S3_BUCKET_NAME.s3.amazonaws.com/ \
     -F "key=$NAME" \
     -F "file=@$NAME" \
     -F "Content-Type=text/plain"
