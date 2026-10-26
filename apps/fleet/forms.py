        champ = self.fields["vehicule"]
        champ.queryset = Vehicule.objects.filter(
            transporteur=transporteur,
            statut=Vehicule.Statut.ACTIF,
            conforme=True,
        )
        champ.empty_label = "Choisissez un véhicule actif et conforme"
        for nom in ("capacite_totale_kg", "capacite_totale_m3", "distance_km"):
            self.fields[nom].required = True
        self.fields["date_depart"].widget.attrs["min"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        if self.instance.pk:
            self.initial["etapes"] = ", ".join(e.ville for e in self.instance.etapes.all())
            # Trajet créé avant la « place proposée » : on repart de la place libre + la part déjà réservée.
            if self.instance.capacite_totale_kg is None:
                self.initial["capacite_totale_kg"] = (
                    self.instance.capacite_dispo_kg + self.instance.capacite_reservee_kg
                )
                self.initial["capacite_totale_m3"] = (
                    self.instance.capacite_dispo_m3 + self.instance.capacite_reservee_m3
                )

    def clean_date_depart(self):
        date = self.cleaned_data["date_depart"]
        if date <= timezone.now():
            raise forms.ValidationError("La date de départ doit être dans le futur.")
        return date

    def clean_etapes(self):
        return [ville.strip() for ville in self.cleaned_data["etapes"].split(",") if ville.strip()]

    def clean(self):
        data = super().clean()
        depart, arrivee = data.get("ville_depart", "").strip(), data.get("ville_arrivee", "").strip()
        if depart and arrivee and depart.casefold() == arrivee.casefold():
            self.add_error("ville_arrivee", "La ville d’arrivée doit être différente de la ville de départ.")

        vehicule, poids, volume = (
            data.get("vehicule"),
            data.get("capacite_totale_kg"),
            data.get("capacite_totale_m3"),
        )
        if poids is not None and poids <= 0:
            self.add_error("capacite_totale_kg", "La place proposée doit être supérieure à 0.")
        elif vehicule and poids and poids > vehicule.capacite_kg:
            self.add_error("capacite_totale_kg", f"Ce véhicule porte au plus {vehicule.capacite_kg} kg.")
        elif self.instance.pk and poids and poids < self.instance.capacite_reservee_kg:
            self.add_error("capacite_totale_kg", "Impossible de proposer moins que la place déjà réservée.")
        if volume is not None and volume <= 0:
            self.add_error("capacite_totale_m3", "La place proposée doit être supérieure à 0.")
        elif vehicule and volume and volume > vehicule.capacite_m3:
            self.add_error("capacite_totale_m3", f"Ce véhicule contient au plus {vehicule.capacite_m3} m³.")
        elif self.instance.pk and volume and volume < self.instance.capacite_reservee_m3:
            self.add_error("capacite_totale_m3", "Impossible de proposer moins que le volume déjà réservé.")
        return data

    def save(self, commit=True):
