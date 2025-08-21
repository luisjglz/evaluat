from django.contrib import admin
from django.apps import apps

# Get all models from the current app
models = apps.get_models()

# Models you want to hide from the admin
excluded_models = ['LogEntry', 'Permission', 'Groups', 'Session', 'ContentType']  # <- use class names here

for model in models:
    if model.__name__ in excluded_models:
        continue  # skip these models
    else:
        print(model.__name__)
        try:
            admin.site.register(model)
        except admin.sites.AlreadyRegistered:
            pass