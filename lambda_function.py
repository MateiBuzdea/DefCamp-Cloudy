import boto3
import datetime
import json
import re
import csv
import os

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb')
table_name = os.environ['TABLE_NAME']

def s3_to_dynamodb(records):
    for record in records:
        bucket_name = record['s3']['bucket']['name']
        file_key = record['s3']['object']['key']

        s3 = boto3.client('s3')
        obj = s3.get_object(Bucket=bucket_name, Key=file_key)
        data = obj['Body'].read().decode('utf-8')

        current_date = datetime.datetime.now().isoformat()

        csv_reader = csv.DictReader(data.splitlines())
        for row in csv_reader:
            name = row.get('Name')
            secret = row.get('Secret')
            if name and secret:
                dynamodb.put_item(
                    TableName=table_name,
                    Item={
                        'Name': {'S': name},
                        'Secret': {'S': secret},
                        'Date': {'S': current_date}
                    }
                )

def query_dynamodb(search):
    scan_filter = '''
        {
            "Name": {
                "ComparisonOperator": "EQ",
                "AttributeValueList": [{"S": "%s"}]
            }
        }
    ''' % search

    response = dynamodb.scan(
        TableName=table_name,
        ScanFilter=json.loads(scan_filter)
    )

    # Get the first item only
    if 'Items' in response and len(response['Items']) > 0:
        return response['Items'][0]["Secret"]["S"]

    return None

def lambda_handler(event, context):
    # If the event is from S3, add data into DynamoDB
    if 'Records' in event and any(record['eventSource'] == 'aws:s3' for record in event['Records']):
        s3_to_dynamodb(event['Records'])
        return {"statusCode": 200, "body": {"result": "Success"}}

    # If the event is from the function URL or from direct invoke, attempt to query DynamoDB
    search = None
    if 'body' not in event:
        return {"statusCode": 400, "body": {"error": "Invalid search query"}}

    try:
        _body = json.loads(event.get('body'))
        search = _body.get('search')
        is_raw = event.get('isRaw')

        if not is_raw and not re.match(r'^[a-zA-Z0-9_]+$', search):
            return {"statusCode": 400, "body": {"error": "Invalid search query"}}
    except:
        pass

    if not search:
        return {"statusCode": 400, "body": {"error": "No search query provided"}}
    
    secret = query_dynamodb(search)

    return {"statusCode": 200, "body": {"result": secret}}