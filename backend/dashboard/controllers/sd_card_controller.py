from django.shortcuts import render
from .services import sd_card_service

def index(request):
    sd_cards = sd_card_service.get_sd_cards()
    return render(request, 'dashboard/sd_card_index.html', {'sd_cards': sd_cards})

def copy(request, sd_card_id):
    if request.method == 'POST':
        sd_card_service.copy_sd_card(sd_card_id)
        return render(request, 'dashboard/sd_card_copy.html', {'sd_card_id': sd_card_id})
    else:
        sd_card = sd_card_service.get_sd_card(sd_card_id)
        return render(request, 'dashboard/sd_card_detail.html', {'sd_card': sd_card})
