"""
End-to-End Latency Analysis Script
Properly calculates latency from Generator emission to Actuator reception
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import os

def calculate_e2e_latency(csv_file):
    """
    Calculate true end-to-end latency from M.Action generation to M.Result reception
    
    Parameters:
    -----------
    csv_file : str
        Path to the YAFS simulation trace CSV file
    
    Returns:
    --------
    pd.DataFrame
        DataFrame with end-to-end latency per message per app
    """
    
    # Read the trace file
    df = pd.read_csv(csv_file)
    
    # Separate M.Action and M.Result messages
    df_action = df[df['message'] == 'M.Action'].copy().reset_index(drop=True)
    df_result = df[df['message'] == 'M.Result'].copy().reset_index(drop=True)
    
    print(f"Loaded {csv_file}")
    print(f"  M.Action messages: {len(df_action)}")
    print(f"  M.Result messages: {len(df_result)}")
    
    # Build end-to-end latency by correlating M.Action and M.Result
    e2e_data = []
    
    for app_name in df['app'].unique():
        app_actions = df_action[df_action['app'] == app_name].copy()
        app_results = df_result[df_result['app'] == app_name].copy()
        
        print(f"\n  App: {app_name}")
        print(f"    M.Action count: {len(app_actions)}")
        print(f"    M.Result count: {len(app_results)}")
        
        # Match M.Action with M.Result in order (FIFO processing)
        num_matched = min(len(app_actions), len(app_results))
        
        for idx in range(num_matched):
            action_emit_time = app_actions.iloc[idx]['time_emit']
            result_reception_time = app_results.iloc[idx]['time_reception']
            
            # End-to-end latency: from Generator emission to Actuator reception
            e2e_latency = result_reception_time - action_emit_time
            
            # Processing time at DataProcess (approximate)
            processing_time = app_results.iloc[idx]['time_emit'] - app_actions.iloc[idx]['time_reception']
            
            # Network latency (both hops combined)
            network_latency = e2e_latency - processing_time
            
            e2e_data.append({
                'app': app_name,
                'message_id': idx,
                'action_emit': action_emit_time,
                'result_reception': result_reception_time,
                'e2e_latency': e2e_latency,
                'processing_latency': processing_time,
                'network_latency': network_latency,
                'action_reception': app_actions.iloc[idx]['time_reception'],
                'result_emit': app_results.iloc[idx]['time_emit'],
            })
    
    df_e2e = pd.DataFrame(e2e_data)
    return df_e2e


def analyze_and_plot(csv_files, output_dir='.'):
    """
    Analyze multiple simulation runs and create separate plots per application
    
    Parameters:
    -----------
    csv_files : dict
        Dictionary mapping distribution names to CSV file paths
    output_dir : str
        Directory to save plots
    """
    
    results = {}
    
    for dist_type, csv_file in csv_files.items():
        print(f"\n{'='*60}")
        print(f"Processing: {dist_type}")
        print(f"{'='*60}")
        df_e2e = calculate_e2e_latency(csv_file)
        results[dist_type] = df_e2e
        
        # Print statistics
        print(f"\nEnd-to-End Latency Statistics for {dist_type}:")
        print(df_e2e['e2e_latency'].describe())
        print(f"\nProcessing Latency Statistics:")
        print(df_e2e['processing_latency'].describe())
    
    # Get all unique app names
    all_apps = sorted(results['deterministic']['app'].unique().tolist())
    
    # Create separate figures for each application
    for app_name in all_apps:
        
        # Plot 1: Latency Timeline (over time)
        fig, ax = plt.subplots(figsize=(12, 6))
        for dist_type, df_e2e in results.items():
            app_data = df_e2e[df_e2e['app'] == app_name].sort_values('result_reception')
            ax.plot(app_data['result_reception'], app_data['e2e_latency'], 
                   label=dist_type, marker='o', markersize=4, alpha=0.7, linewidth=1.5)
        ax.set_xlabel('Simulation Time (time units)', fontsize=11)
        ax.set_ylabel('End-to-End Latency (time units)', fontsize=11)
        ax.set_title(f'{app_name}: E2E Latency Over Simulation Time', fontsize=13, fontweight='bold')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'e2e_latency_{app_name}_01_timeline.png')
        plt.savefig(output_path, dpi=150)
        print(f"✓ Plot saved to: {output_path}")
        plt.close()
        
        # Plot 2: Box plot comparison for this app
        fig, ax = plt.subplots(figsize=(10, 6))
        data_for_box = [results[dist][results[dist]['app'] == app_name]['e2e_latency'].values 
                        for dist in ['deterministic', 'exponential', 'uniform']]
        bp = ax.boxplot(data_for_box, tick_labels=['Deterministic', 'Exponential', 'Uniform'])
        ax.set_ylabel('End-to-End Latency (time units)', fontsize=11)
        ax.set_title(f'{app_name}: E2E Latency Distribution', fontsize=13, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'e2e_latency_{app_name}_02_boxplot.png')
        plt.savefig(output_path, dpi=150)
        print(f"✓ Plot saved to: {output_path}")
        plt.close()
        
        # Plot 3: Mean latency by distribution
        fig, ax = plt.subplots(figsize=(10, 6))
        means = [results[dist][results[dist]['app'] == app_name]['e2e_latency'].mean() 
                 for dist in ['deterministic', 'exponential', 'uniform']]
        stds = [results[dist][results[dist]['app'] == app_name]['e2e_latency'].std() 
                for dist in ['deterministic', 'exponential', 'uniform']]
        x_pos = range(len(['deterministic', 'exponential', 'uniform']))
        ax.bar(x_pos, means, yerr=stds, capsize=5, alpha=0.7, 
               color=['blue', 'orange', 'green'])
        ax.set_xticks(x_pos)
        ax.set_xticklabels(['Deterministic', 'Exponential', 'Uniform'], fontsize=10)
        ax.set_ylabel('Mean E2E Latency (time units)', fontsize=11)
        ax.set_title(f'{app_name}: Mean Latency Comparison (with Std Dev)', fontsize=13, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'e2e_latency_{app_name}_03_mean.png')
        plt.savefig(output_path, dpi=150)
        print(f"✓ Plot saved to: {output_path}")
        plt.close()
        
        # Plot 4: Latency breakdown (processing vs network)
        fig, ax = plt.subplots(figsize=(10, 6))
        processing = [results[dist][results[dist]['app'] == app_name]['processing_latency'].mean() 
                      for dist in ['deterministic', 'exponential', 'uniform']]
        network = [results[dist][results[dist]['app'] == app_name]['network_latency'].mean() 
                   for dist in ['deterministic', 'exponential', 'uniform']]
        
        x_pos = range(len(['deterministic', 'exponential', 'uniform']))
        ax.bar(x_pos, processing, label='Processing', alpha=0.7, color='skyblue')
        ax.bar(x_pos, network, bottom=processing, label='Network', alpha=0.7, color='coral')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(['Deterministic', 'Exponential', 'Uniform'], fontsize=10)
        ax.set_ylabel('Latency (time units)', fontsize=11)
        ax.set_title(f'{app_name}: Latency Breakdown (Processing vs Network)', fontsize=13, fontweight='bold')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'e2e_latency_{app_name}_04_breakdown.png')
        plt.savefig(output_path, dpi=150)
        print(f"✓ Plot saved to: {output_path}")
        plt.close()
    
    # Print summary statistics - overall and per app
    print("\n" + "="*60)
    print("SUMMARY: END-TO-END LATENCY COMPARISON (ALL APPS)")
    print("="*60)
    
    summary_data = []
    for dist_type, df_e2e in results.items():
        summary_data.append({
            'Distribution': dist_type,
            'Mean E2E (ms)': f"{df_e2e['e2e_latency'].mean():.3f}",
            'Std Dev (ms)': f"{df_e2e['e2e_latency'].std():.3f}",
            'Min (ms)': f"{df_e2e['e2e_latency'].min():.3f}",
            'Max (ms)': f"{df_e2e['e2e_latency'].max():.3f}",
            'Messages': len(df_e2e),
        })
    
    summary_df = pd.DataFrame(summary_data)
    print(summary_df.to_string(index=False))
    
    # Per-app summary
    print("\n" + "="*60)
    print("PER-APPLICATION SUMMARY")
    print("="*60)
    
    for app_name in all_apps:
        print(f"\n{app_name}:")
        app_summary = []
        for dist_type, df_e2e in results.items():
            app_data = df_e2e[df_e2e['app'] == app_name]
            app_summary.append({
                'Distribution': dist_type,
                'Mean': f"{app_data['e2e_latency'].mean():.3f}",
                'Std Dev': f"{app_data['e2e_latency'].std():.3f}",
                'Min': f"{app_data['e2e_latency'].min():.3f}",
                'Max': f"{app_data['e2e_latency'].max():.3f}",
            })
        app_df = pd.DataFrame(app_summary)
        print(app_df.to_string(index=False))


if __name__ == '__main__':
    # Define CSV files for each distribution
    csv_files = {
        'deterministic': './sim_trace_ex2_deterministic_seed_42_run_0.csv',
        'exponential': './sim_trace_ex2_exponential_seed_42_run_1.csv',
        'uniform': './sim_trace_ex2_uniform_seed_42_run_2.csv',
    }
    
    # Check which files exist
    existing_files = {}
    for dist, path in csv_files.items():
        if os.path.exists(path):
            existing_files[dist] = path
        else:
            print(f"Warning: File not found - {path}")
    
    if existing_files:
        analyze_and_plot(existing_files)
    else:
        print("Error: No trace files found. Please run the simulations first.")
