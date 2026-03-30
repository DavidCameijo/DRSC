import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from ex3 import main

def calculate_stats(data):
    # Calculate the mean and 95% Confidence Interval for the given data array
    mean = np.mean(data)
    std = np.std(data)
    n = len(data)
    # 1.96 is the Z-value for a 95% confidence interval
    ci95 = 1.96 * (std / np.sqrt(n)) if n > 1 else 0
    return mean, ci95

# --- Configurations ---
run_counts = [10, 30, 100, 1000] # Number of simulation runs to aggregate
sim_time = 1000
dist_types = ["uniform", "poisson"] # Distributions to analyze
results_folder = "ex2/results_ex2_3"

if not os.path.exists(results_folder):
    os.makedirs(results_folder)

for dist_type in dist_types:
    final_results = {"App_0": [], "App_1": [], "App_2": []}

    for N in run_counts:
        all_runs_latency = {"App_0": [], "App_1": [], "App_2": []}
        
        for i in range(N):
            # We assume the simulations have already been executed using ex2_3.py
            # You only need to load the generated datasets!
            
            # YAFS automatically appends '.csv' to the output name defined in the Sim class
            file_path = f"{results_folder}/sim_trace_{dist_type}_run_{i}.csv"
            
            if not os.path.exists(file_path):
                print(f"File {file_path} not found. Ensure ex2_3.py has been run properly.")
                continue
                
            df = pd.read_csv(file_path)
            
            # To calculate the end-to-end (E2E) latency, we need the original emission time 
            # at the Source (Generator), and not the time_emit from the last hop. 
            # YAFS registers the entire transaction across modules with the same 'id'.
            
            # Filter the dataframe to only include the final reception at the sink module
            df_sink = df[df['type'] == 'SINK_M'].copy()
            
            # Get the original time_emit (the lowest time at which each message 'id' appeared in the network)
            original_emit_times = df.groupby('id')['time_emit'].min()
            
            # Map the initial emission time to the sink dataframe and calculate the true E2E latency
            df_sink['time_emit_orig'] = df_sink['id'].map(original_emit_times)
            df_sink['latency'] = df_sink['time_reception'] - df_sink['time_emit_orig']
            # Calculate the mean latency for each individual application in the current simulation run
            for app_idx in range(3):
                app_name = f"App_{app_idx}"
                app_mean = df_sink[df_sink['app'] == app_name]['latency'].mean()
                if pd.notna(app_mean):
                    all_runs_latency[app_name].append(app_mean)

        for app_idx in range(3):
            # Aggregate the results from all N runs to compute the overall mean and confidence interval
            app_name = f"App_{app_idx}"
            mean_lat, ci = calculate_stats(all_runs_latency[app_name])
            final_results[app_name].append({"N": N, "mean": mean_lat, "ci": ci})

    # --- Generate Plot ---
    plt.figure(figsize=(10, 6))
    for app_idx in range(3):
        app_name = f"App_{app_idx}"
        res_df = pd.DataFrame(final_results[app_name])
        # Plot the mean latency values with error bars representing the 95% confidence interval
        plt.errorbar(res_df['N'], res_df['mean'], yerr=res_df['ci'], fmt='o-', capsize=5, label=f'Average Latency ({app_name})')

    plt.xscale('log') # Logarithmic scale on X axis to better visualize the convergence rate
    plt.xticks(run_counts, [str(val) for val in run_counts])
    plt.xlabel("Number of Simulations (N)")
    plt.ylabel("Total Average Latency (ms)")
    plt.title(f"Exercise 3: Latency Convergence ({dist_type})")
    plt.legend()
    plt.grid(True, which="both", ls="-", alpha=0.5)
    plt.savefig(f"convergencia_{dist_type}.png")
    plt.show()