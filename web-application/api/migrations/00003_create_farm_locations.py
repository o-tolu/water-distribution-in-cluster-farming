from django.db import migrations

def create_farm_locations(apps, schema_editor):
    FarmLocation = apps.get_model('api', 'FarmLocation')
    
    # Create the three fixed farm locations if they don't exist
    farms = [
        {'name': 'A', 'description': 'Farm A Location'},
        {'name': 'B', 'description': 'Farm B Location'},
        {'name': 'C', 'description': 'Farm C Location'},
    ]
    
    for farm in farms:
        FarmLocation.objects.get_or_create(
            name=farm['name'],
            defaults={'description': farm['description']}
        )

def reverse_farm_locations(apps, schema_editor):
    FarmLocation = apps.get_model('api', 'FarmLocation')
    FarmLocation.objects.filter(name__in=['A', 'B', 'C']).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0002_initial'),  # Replace with your previous migration
    ]

    operations = [
        migrations.RunPython(create_farm_locations, reverse_farm_locations),
    ]