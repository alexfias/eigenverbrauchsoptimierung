import pandas as pd
import pypsa
import demandlib.bdew as bdew
import datetime
import os
import numpy as np

#initialise system und füge topologie hinzu
system = pypsa.Network(csv_folder_name='./')
system.add("Bus",'Elektrizität')
system.add("Bus",'Wärme')
system.add("Bus",'Netz')

#füge Wärmepumpe hinzu
system.add("Link",
                "Wärmepumpe",
                bus0="Elektrizität",
                bus1="Wärme",
                p_nom=3,p_nom_extendable=False)

#füge PV-Generator hinzu
system.add("Generator","PV Anlage",
            bus="Elektrizität",
            p_nom=10,
            marginal_cost=0,
            efficiency=1.0,p_nom_extendable=False)

#füge Netzanschluss als Generator hinzu
system.add("Generator","Netz",
            bus="Elektrizität",
            p_nom=1000,
            marginal_cost=50,
            efficiency=1.0)

#und Abnehmer
system.add("Link",
                "Netzeinspeisung",
                bus0="Elektrizität",
                bus1="Netz",
                p_nom=1000,efficiency=0.0,p_nom_extendable=False)

#füge elektrischen Verbrauch hinzu
system.add("Load","Elektrische Last",
                bus="Elektrizität")

#füge Wärmeverbrauch hinzu
system.add("Load","Wärmelast",
                bus="Wärme")

#füge Wärmespeicher hinzu
system.add("StorageUnit",
            "Wärmespeicher",
            bus="Wärme",
            p_nom=30,
            max_hours=1, 
           )
          
#erzeuge COP Wärmepumpe
data = pd.read_csv('ninja_weather_50.9330_6.9800_uncorrected.csv',index_col=1)
data.index = system.snapshots

sink_T = 55. # Annahme DTU



def cop(d):
    #COP für Luftwärmepumpe
    #Formel entstammt Staffell et al. (2012)
    #https://doi.org/10.1039/C2EE22653G
    return 6.81 -0.121*d + 0.000630*d**2


data['COP'] = cop(sink_T-data['temperature'])

#füge PV Erzeugung hinzu
pv_gen= pd.read_csv('ninja_pv_50.9330_6.9800_corrected.csv')['electricity']
pv_gen.index = data.index
data['pv_gen'] = pv_gen


#Lastprofil Wärme
temperature = data['temperature']

holidays = {}

demand = pd.DataFrame(
        index=pd.date_range(pd.datetime(2019, 1, 1, 0),
                            periods=8760, freq='H'))
demand['heat'] = bdew.HeatBuilding(
        demand.index, holidays=holidays, temperature=temperature,
        shlp_type='EFH',
        building_class=1, wind_class=1, annual_heat_demand=10000,
        name='EFH').get_bdew_profile()

demand.index = data.index

#Lastprofil Strom
year=2019
e_slp = bdew.ElecSlp(year, holidays=holidays)
ann_el_demand_per_sector = {
        'g0': 0,
        'h0': 3500,
        'i0': 0,
        'i1': 0,
        'i2': 0,
        'g6': 0}
elec_demand = e_slp.get_profile(ann_el_demand_per_sector)
elec_demand = elec_demand.resample('H').mean()
elec_demand.index = data.index

data['heat demand'] = demand['heat']
data['electricity demand'] = elec_demand['h0']
system.loads_t.p_set['Elektrische Last'] = data['electricity demand']
system.loads_t.p_set['Wärmelast']=data['heat demand']



#füge potenzielle Erzeugung PV Anlage und COP Wärmepumpe hinzu
system.generators_t.p_max_pu['PV Anlage'] = data['pv_gen']
system.links_t.efficiency['Wärmepumpe'] = data['COP']



#Optimierungsproblem
system.lopf(solver_name='gurobi')


#plotte Eigenverbrauch
import matplotlib.pyplot as plt
system.generators_t.p.resample('M').mean()
fig=(system.generators_t.p.resample('M').mean()/system.generators_t.p_max_pu.resample('M').mean()/10.).plot(kind='bar',stacked=True).get_figure()
plt.show()
fig.tight_layout()
fig.savefig('eigenverbrauch_mit_wp.pdf')

#plotte und speichere Eigenverbrauch
import matplotlib.pyplot as plt
import calendar

plt.figure()
ax=(system.generators_t.p.resample('M').mean()['PV Anlage']/system.generators_t.p_max_pu.resample('M').mean()['PV Anlage']/10.).plot(kind='bar',stacked=True)#.get_figure()
plt.ylabel('Eigenverbrauch')
plt.title('Eigenverbrauch PV Anlage mit Wärmepumpe')
ax.set_xticklabels( calendar.month_name[1:13], rotation=50)
plt.tight_layout()
plt.savefig('eigenverbrauch_mit_wp.pdf')
