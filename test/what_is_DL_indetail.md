Deep learning is a subset of machine learning that trains **multi-layer** (deep) neural networks to learn representations from data and make predictions or decisions. It is “deep” because it stacks multiple layers that progressively turn raw inputs (pixels, waveforms, tokens) into higher-level features useful for the task. [ibm](https://www.ibm.com/think/topics/deep-learning)

## Core idea: representation learning
Instead of relying on hand-designed features, deep learning learns features automatically from data (feature learning). Early layers often capture simple patterns (e.g., edges in images), while deeper layers combine them into more complex concepts (e.g., parts → objects). [meltwater](https://www.meltwater.com/en/blog/fundamentals-of-deep-learning)

## Model anatomy (what “a deep network” contains)
A typical neural network has an input layer, multiple hidden layers, and an output layer. Each layer applies a weighted transformation plus a nonlinear activation, which lets the model represent complex, nonlinear relationships. [datacamp](https://www.datacamp.com/tutorial/tutorial-deep-learning-tutorial)

## Training loop (how it learns)
Training usually follows a repeated cycle: forward propagation to produce an output, compute a loss by comparing with the target, backpropagation to compute gradients, then update weights with an optimizer such as gradient descent. This process repeats over many iterations/epochs until the error is reduced and the model fits the training data well. [test-king](https://www.test-king.com/blog/deep-learning-fundamentals-a-beginners-complete-guide/)

## Key hyperparameters and practical knobs
Common hyperparameters include learning rate, batch size, and number of epochs; they strongly affect speed of learning, stability, and whether the model underfits or overfits. In practice, regularization and validation monitoring are used to control overfitting and improve generalization to unseen data. [datacamp](https://www.datacamp.com/tutorial/tutorial-deep-learning-tutorial)

## Common architectures and what they’re good at
- CNNs: strong for images because convolutions learn local spatial patterns and build hierarchies of visual features. [developer.nvidia](https://developer.nvidia.com/blog/deep-learning-nutshell-core-concepts/)
- Transformers: widely used for sequence modeling (especially language), and underpin many modern large-scale models. [introtodeeplearning](https://introtodeeplearning.com)
- GANs: generative models with a generator and discriminator trained in competition to synthesize realistic samples. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC8372231/)

If you share the domain you care about (vision, NLP, speech, recommender systems), I can explain the most relevant architecture and the typical training setup in that domain.