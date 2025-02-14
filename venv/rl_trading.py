import os
import sys
import pandas as pd
import numpy as np
import gym
from gym import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.evaluation import evaluate_policy
import contextlib

def main():
    # -------------------------------
    # Step 1: Load & Preprocess the Data
    # -------------------------------
    csv_path = r"C:\Users\User\AppData\Roaming\JetBrains\PyCharmCE2023.1\scratches\Statement.csv"
    if not os.path.exists(csv_path):
        print(f"❌ ERROR: CSV file not found at path: {csv_path}")
        sys.exit(1)

    # Read the CSV (comma-delimited)
    df = pd.read_csv(csv_path, delimiter=",")
    print("✅ Shape of DataFrame after reading CSV:", df.shape)

    # Rename columns for clarity.
    df.columns = ["ticket", "open_time", "trade_type", "size", "item", "open_price",
                  "s_l", "t_p", "close_time", "close_price", "commission", "taxes", "swap", "profit"]

    # Keep only relevant columns.
    df = df[["open_time", "trade_type", "size", "item", "profit"]]

    # Convert "open_time" to a scaled timestamp.
    df["open_time"] = pd.to_datetime(df["open_time"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    df["open_time"] = (df["open_time"].astype(np.int64) / 1e9).astype(np.float32)

    # Encode "trade_type" (1 for buy, 0 for sell).
    df["trade_type"] = df["trade_type"].apply(lambda x: 1 if x.lower() == "buy" else 0)

    # Convert "size" and "profit" to numeric.
    df["size"] = pd.to_numeric(df["size"], errors="coerce")
    df["profit"] = pd.to_numeric(df["profit"], errors="coerce")

    # Convert 'item' to numeric using factorization.
    df["item"], item_labels = pd.factorize(df["item"])

    # Compute historical profitability for each asset (item)
    item_avg_profit = df.groupby("item")["profit"].mean().to_dict()
    df["item_avg_profit"] = df["item"].map(item_avg_profit)

    # Add Rolling Mean Profit (Last 5 Trades) as a Feature
    df["rolling_profit"] = df["profit"].rolling(window=5, min_periods=1).mean()

    # -------------------------------
    # Step 2: Display Key Statistics
    # -------------------------------
    print("\n🔍 **Dataset Summary:**")
    print(df.describe())

    # Compute mean & standard deviation of profit for Sharpe Ratio Reward
    profit_mean = df["profit"].mean()
    profit_std = df["profit"].std() + 1e-6  # Avoid division by zero

    df.to_csv("Modified_Statement_debug.csv", index=False)
    print("✅ Modified statement saved as Modified_Statement_debug.csv (after preprocessing).")

    # -------------------------------
    # Step 3: Define Custom Trading Environment
    # -------------------------------
    class TradingEnv(gym.Env):
        """
        Improved trading environment:
          - Reward: Sharpe Ratio-Based Reward
          - Observation: [open_time, trade_type, size, item, item_avg_profit, rolling_profit]
        """
        metadata = {'render.modes': ['human']}

        def __init__(self, dataframe, profit_mean, profit_std):
            super(TradingEnv, self).__init__()
            self.df = dataframe.reset_index(drop=True)
            self.current_step = 0
            self.profit_mean = profit_mean
            self.profit_std = profit_std

            self.action_space = spaces.Discrete(2)
            self.observation_space = spaces.Box(low=0, high=np.inf, shape=(6,), dtype=np.float32)

        def _get_obs(self):
            row = self.df.iloc[self.current_step]
            obs = np.array([
                row["open_time"],
                row["trade_type"],
                row["size"],
                row["item"],
                row["item_avg_profit"],
                row["rolling_profit"]
            ], dtype=np.float32)
            return obs

        def reset(self):
            self.current_step = 0
            return self._get_obs()

        def step(self, action):
            done = False
            row = self.df.iloc[self.current_step]

            # Sharpe Ratio-Based Reward
            if action == 1:
                sharpe_reward = (row["profit"] - self.profit_mean) / self.profit_std
            else:
                sharpe_reward = 0  # If trade is skipped

            self.current_step += 1
            if self.current_step >= len(self.df):
                done = True
                next_obs = np.zeros(self.observation_space.shape, dtype=np.float32)
            else:
                next_obs = self._get_obs()

            return next_obs, sharpe_reward, done, {}

    env = TradingEnv(df, profit_mean, profit_std)

    # -------------------------------
    # Step 4: Train an RL Agent using PPO
    # -------------------------------
    model = PPO("MlpPolicy", env, verbose=1, ent_coef=0.02)  # Increase entropy to encourage exploration
    model.learn(total_timesteps=50000)

    mean_reward, std_reward = evaluate_policy(model, env, n_eval_episodes=10)
    print(f"\n🏆 **Evaluation: Mean Reward = {mean_reward:.2f} ± {std_reward:.2f}**")

    # -------------------------------
    # Step 5: Analyze Agent Decisions
    # -------------------------------
    actions = []
    obs = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        actions.append(action)
        obs, reward, done, _ = env.step(action)

    df["action"] = actions
    df.to_csv("Modified_Statement_debug.csv", index=False)
    print("✅ Modified statement saved as Modified_Statement_debug.csv (after simulation).")


if __name__ == '__main__':
    # Redirect all print statements to a log file with UTF-8 encoding.
    with open("training_log.txt", "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(log_file):
            main()
