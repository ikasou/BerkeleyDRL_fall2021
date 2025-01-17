import numpy as np

from .base_policy import BasePolicy


class MPCPolicy(BasePolicy):

    def __init__(self,
                 env,
                 ac_dim,
                 dyn_models,
                 horizon,
                 N,
                 sample_strategy='random',
                 cem_iterations=4,
                 cem_num_elites=5,
                 cem_alpha=1,
                 **kwargs
                 ):
        super().__init__(**kwargs)

        # init vars
        self.env = env
        self.dyn_models = dyn_models
        self.horizon = horizon
        self.N = N
        self.data_statistics = None  # NOTE must be updated from elsewhere

        self.ob_dim = self.env.observation_space.shape[0]

        # action space
        self.ac_space = self.env.action_space
        self.ac_dim = ac_dim
        self.low = self.ac_space.low
        self.high = self.ac_space.high

        # Sampling strategy
        allowed_sampling = ('random', 'cem')
        assert sample_strategy in allowed_sampling, f"sample_strategy must be one of the following: {allowed_sampling}"
        self.sample_strategy = sample_strategy
        self.cem_iterations = cem_iterations
        self.cem_num_elites = cem_num_elites
        self.cem_alpha = cem_alpha

        print(f"Using action sampling strategy: {self.sample_strategy}")
        if self.sample_strategy == 'cem':
            print(f"CEM params: alpha={self.cem_alpha}, "
                + f"num_elites={self.cem_num_elites}, iterations={self.cem_iterations}")

    def sample_action_sequences(self, num_sequences, horizon, obs=None):
        if self.sample_strategy == 'random' or (self.sample_strategy == 'cem' and obs is None):
            # TODO(Q1) uniformly sample trajectories and return an array of
            # dimensions (num_sequences, horizon, self.ac_dim) in the range
            # [self.low, self.high]
            return self.low + (self.high - self.low)*np.random.rand(num_sequences, horizon, self.ac_dim).astype(np.float32)
        elif self.sample_strategy == 'cem':
            # TODO(Q5): Implement action selection using CEM.
            # Begin with randomly selected actions, then refine the sampling distribution
            # iteratively as described in Section 3.3, "Iterative Random-Shooting with Refinement" of
            # https://arxiv.org/pdf/1909.11652.pdf
            RNG = np.random.default_rng()
            for i in range(self.cem_iterations):
                # - Sample candidate sequences from a Gaussian with the current
                #   elite mean and variance
                #     (Hint: remember that for the first iteration, we instead sample
                #      uniformly at random just like we do for random-shooting)
                # - Get the top `self.cem_num_elites` elites
                #     (Hint: what existing function can we use to compute rewards for
                #      our candidate sequences in order to rank them?)
                # - Update the elite mean and variance
                # ILK best to use truncated normals: from x -> cumnorm(x) properly adjusted 
                if i > 0: 
                    candidate_action_sequences = np.array([
                        RNG.multivariate_normal(elite_mean_at_t[t, :], np.diag(elite_stddev_at_t[t, :]), num_sequences)
                        for t in range(horizon) ])
                    candidate_action_sequences = np.fmax(self.low, np.fmin(self.high, candidate_action_sequences)).astype(np.float32)
                    candidate_action_sequences = candidate_action_sequences.transpose([1, 0, 2])
                else: #return random the first time
                    candidate_action_sequences = self.low + \
                        (self.high - self.low)*np.random.rand(num_sequences, horizon, self.ac_dim).astype(np.float32)
                predicted_rewards = self.evaluate_candidate_sequences(candidate_action_sequences, obs)
                elite_indices = np.argsort(predicted_rewards)[-self.cem_num_elites:]
                if (i > 0) and (i < self.cem_iterations - 1):
                    elite_mean_at_t = self.cem_alpha * elite_mean_at_t + \
                        np.mean(candidate_action_sequences[elite_indices, :, :], axis = 0, dtype=np.float32, keepdims=False)
                    elite_stddev_at_t = self.cem_alpha * elite_stddev_at_t + \
                        np.std(candidate_action_sequences[elite_indices, :, :], axis = 0, dtype=np.float32, keepdims=False)
                else:
                    elite_mean_at_t = np.mean(candidate_action_sequences[elite_indices, :, :], axis = 0, dtype=np.float32, keepdims=False)
                    elite_stddev_at_t = np.std(candidate_action_sequences[elite_indices, :, :], axis = 0, dtype=np.float32, keepdims=False)/4 #hack
                
            # TODO(Q5): Set `cem_action` to the appropriate action sequence chosen by CEM.
            # The shape should be (horizon, self.ac_dim)
            cem_action = candidate_action_sequences[elite_indices[-1], :, :]

            return cem_action[None]
        else:
            raise Exception(f"Invalid sample_strategy: {self.sample_strategy}")

    def evaluate_candidate_sequences(self, candidate_action_sequences, obs):
        # TODO(Q2): for each model in ensemble, compute the predicted sum of rewards
        # for each candidate action sequence.
        #
        # Then, return the mean predictions across all ensembles.
        # Hint: the return value should be an array of shape (N,)
        sum_rew = None
        for model in self.dyn_models:
            if sum_rew is None:
                sum_rew = self.calculate_sum_of_rewards(obs, candidate_action_sequences, model)
            else:
                sum_rew = np.column_stack((sum_rew, self.calculate_sum_of_rewards(obs, candidate_action_sequences, model)))

        return np.mean(sum_rew, axis=1, keepdims=False)

    def get_action(self, obs):
        if self.data_statistics is None:
            return self.sample_action_sequences(num_sequences=1, horizon=1)[0]

        # sample random actions (N x horizon)
        candidate_action_sequences = self.sample_action_sequences(
            num_sequences=self.N, horizon=self.horizon, obs=obs)

        if candidate_action_sequences.shape[0] == 1:
            # CEM: only a single action sequence to consider; return the first action
            return candidate_action_sequences[0][0][None]
        else:
            predicted_rewards = self.evaluate_candidate_sequences(candidate_action_sequences, obs)

            # pick the action sequence and return the 1st element of that sequence
            best_action_sequence = np.argmax(predicted_rewards)  # TODO (Q2)
            action_to_take = candidate_action_sequences[best_action_sequence, 0, :]  # TODO (Q2)
            return action_to_take[None]  # Unsqueeze the first index

    def calculate_sum_of_rewards(self, obs, candidate_action_sequences, model):
        """
        :param obs: numpy array with the current observation. Shape [D_obs]
        :param candidate_action_sequences: numpy array with the candidate action
        sequences. Shape [N, H, D_action] where
            - N is the number of action sequences considered
            - H is the horizon
            - D_action is the action of the dimension
        :param model: The current dynamics model.
        :return: numpy array with the sum of rewards for each action sequence.
        The array should have shape [N].
        """
        # For each candidate action sequence, predict a sequence of
        # states for each dynamics model in your ensemble.
        # Once you have a sequence of predicted states from each model in
        # your ensemble, calculate the sum of rewards for each sequence
        # using `self.env.get_reward(predicted_obs, action)` at each step.
        # You should sum across `self.horizon` time step.
        # Hint: you should use model.get_prediction and you shouldn't need
        #       to import pytorch in this file.
        # Hint: Remember that the model can process observations and actions
        #       in batch, which can be much faster than looping through each
        #       action sequence.
        N, H, D_ac = candidate_action_sequences.shape
        D_ob = len(obs)
        predicted_obs = np.ndarray((N, H, D_ob), dtype=np.float32)
        rewards = np.ndarray((N, H, 1), dtype=np.float32)
        for h in range(H):  
            used_obs = predicted_obs[:, h-1, :] if h>0 else np.broadcast_to(obs, (N, D_ob))
            ac_seq = candidate_action_sequences[:, h, :]
            predicted_obs[:, h, :] = model.get_prediction(used_obs, ac_seq, self.data_statistics)
            
        rewards, dones = self.env.get_reward(predicted_obs.reshape(N*H, D_ob), candidate_action_sequences.reshape(N*H, D_ac))
        truncated_rewards = rewards*(1-dones)  # should be able to do this given C row-major ordering is default
        sum_of_rewards = np.sum(rewards.reshape(N, H), axis=1, keepdims=False)  # TODO (Q2)
        return sum_of_rewards
