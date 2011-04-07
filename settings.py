DEBUG = False
SECRET_KEY = 'A_UNIQUE_KEY_FOR_YOUR_APPLICATION'

AWS_ACCESS_KEY_ID = 'YOUR_AWS_ACCESS_KEY_ID'
AWS_SECRET_ACCESS_KEY = 'YOUR_AWS_SECRET_ACCESS_KEY'
AWS_BUCKET = 'YOUR_S3_BUCKET'
AWS_DISTRIBUTION_ID = 'YOUR_CLOUDFRONT_DISTRO_ID'

LYDON_WORKING_DIR = 'YOUR_WORKING_DIRECTORY'
LYDON_CACHE_TIMEOUT = 60*60*24*365*10  # 10 years

LYDON_OAUTH_KEYS = [{'key': 'CONSUMER_KEY_1',
                     'secret': 'CONSUMER_SECRET_1',
                     'namespace': 'NAMESPACE_1'}, ]