import json, os
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy, reverse
#from .forms import *
from .models import *
from django.views.decorators.csrf import csrf_exempt
from django.core import serializers
from django.db.models import Q, Count, F, OuterRef, Subquery, DateTimeField, Exists
from datetime import datetime
from django.core.paginator import Paginator
from django.template.loader import get_template
#from xhtml2pdf import pisa
from io import BytesIO
from django.contrib.auth.hashers import make_password
from django.shortcuts import get_object_or_404
from collections import defaultdict
from pathlib import Path
from django.db import transaction



def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")
# Create your views here.


def homepage(request):
    if (request.method == "POST"):
        username = request.POST["usuario"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next') or 'mainadminview'
            return redirect(next_url)
        else:
            messages.error(request, ("Login o password incorrecto"))
            return redirect('homepage')
    #return render(request, 'homepage.html', {'next': request.GET.get('next', '')})
    #return HttpResponse("Hello, world. You're at the polls index.")
    #return redirect('homepage')
    return render(request, 'homepage.html', {'next': request.GET.get('next', '')})