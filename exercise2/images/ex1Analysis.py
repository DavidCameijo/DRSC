import pandas as pd
import matplotlib.pyplot as plt

# 1. Load the simulation trace
df = pd.read_csv('sim_trace_ex1.csv')

# 2. Calculate Latency
df['latency'] = df['time_reception'] - df['time_emit']

# 3. Setup Plot
plt.figure(figsize=(12, 6))
colors = {'App_0': 'red', 'App_1': 'blue', 'App_2': 'green'}
markers = {'App_0': 'o', 'App_1': 's', 'App_2': '^'}

# 4. Plot each app
for app_name in sorted(df['app'].unique()):
    app_data = df[df['app'] == app_name].sort_values(by='time_reception')
    plt.plot(app_data['time_reception'], app_data['latency'],
             label=app_name,
             color=colors.get(app_name),
             marker=markers.get(app_name),
             markersize=4,
             linestyle='-',
             alpha=0.8)

# 5. Add the Vertical Bar at Simulation Time = 50
plt.axvline(x=50, color='purple', linestyle='--', linewidth=2, label='Link (0,1) Failure')

# 6. Add a text annotation for clarity
plt.text(51, df['latency'].max() * 0.9, 'Link (0,1) Failure\nat t=50s', color='purple', fontweight='bold')

# 7. Formatting
plt.xlim(0, 100)
plt.title('Impact of Link Failure on Application Latency')
plt.xlabel('Simulation Time (s)')
plt.ylabel('Latency (ms)')
plt.legend()
plt.grid(True, linestyle=':', alpha=0.6)

# 8. Save
plt.savefig('activity1_with_failure_bar.png')
plt.show()