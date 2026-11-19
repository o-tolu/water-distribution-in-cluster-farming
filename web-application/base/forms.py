from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.exceptions import ValidationError
from .models import CustomUser
import re


class CustomUserCreationForm(UserCreationForm):
    rfid_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    matric_number = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'firstname', 'lastname', 'mobile', 'rfid_number', 'matric_number', 'password1', 'password2']

    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data.get('rfid_number'):
            self.add_error('rfid_number', 'RFID number is required')
        if not cleaned_data.get('matric_number'):
            self.add_error('matric_number', 'Matric number is required')

        return cleaned_data
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        if not password1 or not password2:
            raise ValidationError("Both password fields are required.")

        if password1 != password2:
            raise ValidationError("Passwords do not match.")

        if len(password1) < 8:
            raise ValidationError("Password must be at least 8 characters long.")

        if not re.search(r'[A-Z]', password1):
            raise ValidationError("Password must contain at least one uppercase letter.")

        if not re.search(r'\d', password1):
            raise ValidationError("Password must contain at least one digit.")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password1):
            raise ValidationError("Password must contain at least one special character.")

        return password2


    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if mobile:
            # Remove any spaces or special characters
            mobile = ''.join(filter(str.isdigit, mobile))
            
            # Check if number starts with 0 and remove it
            if mobile.startswith('0'):
                mobile = mobile[1:]
            
            # Add +234 prefix if not present
            if not mobile.startswith('234'):
                mobile = '234' + mobile
            
            # Add + to the beginning
            mobile = '+' + mobile
            
            # Validate length and format
            if not re.match(r'^\+234[789][01]\d{8}$', mobile):
                raise forms.ValidationError('Enter a valid Nigerian phone number')
            
        return mobile

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.username:
            user.username = user.email.split('@')[0]

        # Public registration must always create an ordinary farmer account.
        user.is_admin = False
        user.is_superuser = False

        if commit:
            user.save()
        return user


class AdminUserCreationForm(CustomUserCreationForm):
    """Form used exclusively by authenticated admins to create another admin account."""

    class Meta(CustomUserCreationForm.Meta):
        fields = ['email', 'firstname', 'lastname', 'mobile', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('rfid_number', None)
        self.fields.pop('matric_number', None)

    def clean(self):
        return UserCreationForm.clean(self)

    def save(self, commit=True):
        user = UserCreationForm.save(self, commit=False)
        if not user.username:
            user.username = user.email.split('@')[0]
        user.is_admin = True
        user.is_superuser = False
        user.rfid_number = None
        user.matric_number = None
        if commit:
            user.save()
        return user



from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            self.user_cache = authenticate(username=username, password=password)

            if self.user_cache is None:
                raise forms.ValidationError("Invalid username or password.")

        return self.cleaned_data

class MyPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label='Old Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': ' ',
            'autocomplete': 'current-password',  # Add autocomplete
        })
    )
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': ' ',
            'autocomplete': 'new-password',  # Add autocomplete
        })
    )
    new_password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': ' ',
            'autocomplete': 'new-password',  # Add autocomplete
        })
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.user = user  # Explicitly set the user

    def clean_old_password(self):
        old_password = self.cleaned_data.get('old_password')
        if not self.user.check_password(old_password):
            raise forms.ValidationError("Your old password was entered incorrectly. Please enter it again.")
        return old_password

class MyPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': ' ',
        })
    )

class MySetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': ' ',
        })
    )
    new_password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': ' ',
        })
    )