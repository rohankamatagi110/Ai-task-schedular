# AI Task Scheduling App

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Google Cloud Credentials

To use the Dialogflow integration, you need to set up a service account key:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (taskscheduler-irmq)
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "Service Account"
5. Fill in the details and click "Create"
6. Grant the service account the "Dialogflow API Client" role
7. Create a key for this service account (JSON format)
8. Download the key file and replace the placeholder values in `scheduler/taskscheduler-service-account.json` with your actual service account key information

### 3. Run the Application

```bash
python manage.py runserver
```

## Troubleshooting

### Dialogflow Import Error

If you encounter an error like `cannot import name 'dialogflow_v2' from 'google.cloud'`, make sure:

1. You have installed the correct version of the Dialogflow package: `pip install google-cloud-dialogflow==2.35.0`
2. You have set up the service account key file correctly
3. The `GOOGLE_APPLICATION_CREDENTIALS` environment variable is set correctly in `settings.py`

### Authentication Issues

If you encounter authentication issues with Dialogflow:

1. Verify that your service account key file contains all required fields (type, project_id, private_key, client_email, etc.)
2. Make sure the service account has the necessary permissions for Dialogflow
3. Check that the project ID in your service account key matches the `DIALOGFLOW_PROJECT_ID` in settings.py