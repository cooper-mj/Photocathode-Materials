#!/usr/bin/env python

import argparse
import itertools
import math
import numpy as np
import random
import torch
import torch.nn as nn
import torch.optim as optim
import pickle

from discriminator import Discriminator
from gan import load_dataset, batch_dataset, train, gen_noise
from generator import Generator
from utils import load_dataset
from logger_utils import Logger
from matplotlib import pyplot as plt
from torch.autograd import Variable
from torchvision import transforms, datasets


# ==============================================================================
# Distillation GAN
# ==============================================================================
def get_training_partitions(X):
    """
    Generates column-partitioned training sets for various GANs
    # TODO: for an extension, we can sample a number of random datasets
    """
    X = torch.tensor(X, dtype=torch.float32)

    other_idx = [i for i in range(0,7)]
    other_X = X[:,:,other_idx]

    atomic_idx = [i for i in range(7,71,4)]
    atomic_X = X[:,:,atomic_idx]

    locations_idx = [i for i in range(8,71) if i % 4 != 3]
    locations_X = X[:,:,locations_idx]

    return [(other_X, other_idx), (atomic_X, atomic_idx), (locations_X, locations_idx)]


def init_population(X, num_batches):
    """
    Initializes a population given the initial training partitions
    """
    partitions = get_training_partitions(X)
    generation = 0
    population = dict()
    for i, partition in enumerate(partitions):
        spec_args = args
        spec_args.g_input_size = args.latent
        spec_args.g_output_size = len(partition)
        spec_args.g_hidden_size = int(math.ceil(spec_args.g_output_size / 2))
        spec_args.d_input_size = len(partition)
        spec_args.d_hidden_size = int(math.ceil(spec_args.d_input_size / 2))

        print(partition[0].shape)
        G, D, _, evaluations = train(
            partition[0],
            num_batches,
            args.num_particle_samples,
            set_args=spec_args
        )
        MLE_emittance = torch.mean(evaluations)
        population['gen%dpartition%d' % (generation, i)] = {
            'generator': G,
            'discriminator': D,
            'emittance': MLE_emittance,
            'partition': partition
        }
    return population


def mutate(population, num_batches, generation):
    """
    Trains a GAN for each population element
    """
    population = dict()
    i = 0
    for label, map in population.items():
        G, D, _, evaluations = train(
            map['partition'][0],
            num_batches,
            args.num_particle_samples,
            G=map['generator'],
            D=map['discriminator'],
            set_args=args
        )
        MLE_emittance = torch.mean(evaluations)
        population['gen%dpartition%d' % (generation, i)] = {
            'generator': G,
            'discriminator': D,
            'emittance': MLE_emittance,
            'partition': partition
        }
        i += 1
    return population


def select_k_fittest(population, k):
    """
    Select k fittest GANs
    TODO: debug this function
    """
    if len(population) <= k:
        sorted_population = sorted(population.items(), key=lambda kv: kv[1]['emittance'])[:k]  # results in a list of tuples
    else:
        sorted_population = population
    parents = {tuple[0]: tuple[1] for tuple in sorted_population}
    return parents


def crossover(pol1, pol2, pol3):
    """
    Genetic operator that crosses together two GANs trained separately
    Specifically for our case, we note our child GANS train on different parts
    of the dataset. Hence, we combine to create a new good dataset extension
    to match with a new student GAN.

    We choose the crossover to operate on 3 GANs for the initial combination of the dataset
    """
    G_1 = pol1['generator']
    p_1 = pol1['partition']

    G_2 = pol2['generator']
    p_2 = pol2['partition']

    G_3 = pol3['generator']
    p_3 = pol3['partition']

    test_noise_1 = gen_noise(args.crossover_samples, args.latent)
    test_noise_2 = gen_noise(args.crossover_samples, args.latent)
    test_noise_3 = gen_noise(args.crossover_samples, args.latent)

    fake_data_1 = G_1(test_noise_1).detach()  # make sure when we create a gan we can set its output shape (critical!)
    fake_data_2 = G_2(test_noise_2).detach()
    fake_data_3 = G_3(test_noise_3).detach()

    # Format back into their appropriate columns
    d_1 = torch.zeros(args.crossover_samples, 71)
    d_2 = torch.zeros(args.crossover_samples, 71)
    d_3 = torch.zeros(args.crossover_samples, 71)

    print(fake_data_1.shape)
    print(d_1[:,p_1[1]].shape)
    d_1[:,p_1[1]] = fake_data_1
    d_2[:,p_2[1]] = fake_data_2
    d_3[:,p_3[1]] = fake_data_3

    # Also format the datasets back into their appropriate columns
    jp_1 = torch.zeros(71)
    jp_2 = torch.zeros(71)
    jp_3 = torch.zeros(71)

    jp_1[:,p_1[1]] = p_1[0]
    jp_2[:,p_2[1]] = p_2[0]
    jp_3[:,p_3[1]] = p_3[0]

    joint_partition = torch.cat((p_1[0], p_2[0], p_3[0]), dim=1)

    # ======================================================================== #
    # Construction Zone:
    #   We need to build an optimizer to optimize for low emittance value
    #   selecting from column values either from d_1, d_2 or d_3 for each
    #   column
    # ======================================================================== #
    # N =
    # if args.optim == 'Adam':
    #     optimizer = optim.Adam(N.parameters(), lr=args.d_learning_rate)
    # else:
    #     optimizer = optim.SGD(N.parameters(), lr=args.d_learning_rate)

    # For each generated feature col, choose the col that maximizes according to NN_eval (stochastic gradient descent or adam)
        # After this, we already have a sub-GAN which is SGD optimized GAN combination
        # This is what Michael was originally interested in investigating
        # The only problem is this is not a single GAN, so we cannot add it to a population and iterate
        # Print the results (i.e. mean emittance for the crossover) for sure!
    # ======================================================================== #
    # Construction Zone:
    #   We need to build an optimizer to optimize for low emittance value
    #   selecting from column values either from d_1, d_2 or d_3 for each
    #   column
    # ======================================================================== #

    joint_partition = torch.cat((joint_partition, gen_partition), dim=0)
    # ======================================================================== #
    # Construction Zone:
    #   We need to create a new tensor to only choose rows that have top 20%
    #   emittance values. Do this using tensor math only so fast
    # ======================================================================== #
    # TODO: for each row in top_partition, get the emittance value, and then select the top 20% rows by emittance value
    # ======================================================================== #
    # Construction Zone:
    #   We need to create a new tensor to only choose rows that have top 20%
    #   emittance values. Do this using tensor math only so fast
    # ======================================================================== #

    # Now that we have a new dataset, train a new GAN on it for imitation learning GAN.
    # This takes it a step further by allowing multiple epochs of GPO
    return train(
        top_partition,
        num_batches,
        args.num_particle_samples,
        set_args=args
    )


def breed(parents, population):
    """
    Runs crossover and 'dagger'_distillation on pairs of fit parents
    """
    children = dict()

    triplets = list(itertools.combinations(parents.values(), 3))
    while len(population) - len(triplets) > 0:
        triplets.append(random.choice(triplets))
    if len(triplets) - len(population) > 0:
        triplets = random.sample(triplets, len(population))

    w = 0
    for p1, p2, p3 in triplets:
        G, D, _, evaluations = crossover(p1, p2, p3)
        MLE_emittance = torch.mean(evaluations)

        children['cross%d' % w] = {
            'generator': G,
            'discriminator': D,
            'emittance': MLE_emittance,
            'partition': partition
        }
        w += 1
    return children


def train_GPO_GAN(X, Y, num_batches, k, r):
    """
    Trains a student GAN network from a teacher GAN selected from population and r epochs
        Specifically for our project, we would like to experiment with
        generating our atomic numbers and connections separately, to do this,
        we distill a GAN trained on atomic numbers and a GAN trained on connections
        into a binary GAN policy and train a student using a framework similar
        to GPO (https://arxiv.org/pdf/1711.01012.pdf)

    We have modified this framework specifically to train GANs on various parts
    of the dataset separately.
    """
    population = init_population(X, num_batches)
    epoch = 0

    while epoch < r and len(population) > 1:
        if epoch > 0:
            population = mutate(population, num_batches, epoch)
        parents = select_k_fittest(population, k)
        population = breed(parents, population)
        epoch += 1

    # Run a final training on the resultant child to ensure training on full dataset
    student = select_k_fittest(population, 1)  # probably bug, need to isolate a single particle rather than a dict
    return train(
        X,
        num_batches,
        args.num_particle_samples,
        student['generator'],
        student['discriminator'],
        set_args=args
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--latent', type=int, default=8, help="Latent representation size")
    parser.add_argument('--g_input_size', type=int, default=8, help="Random noise dimension coming into generator, per output vector")
    parser.add_argument('--g_hidden_size', type=int, default=32, help="Generator complexity")
    parser.add_argument('--g_output_size', type=int, default=71, help="Size of generator output vector")

    parser.add_argument('--d_input_size', type=int, default=71, help="Minibatch size - cardinality of distributions (change)")
    parser.add_argument('--d_hidden_size', type=int, default=32, help="Discriminator complexity")
    parser.add_argument('--d_output_size', type=int, default=1, help="Single dimension for real vs fake classification")

    parser.add_argument('--p', type=float, default=0.2)
    parser.add_argument('--dropout', type=float, default=0.3)

    parser.add_argument('--d_learning_rate', type=float, default=1e-3)
    parser.add_argument('--g_learning_rate', type=float, default=1e-3)
    parser.add_argument('--sgd_momentum', type=float, default=0.9)

    parser.add_argument('--num_epochs', type=int, default=200)
    parser.add_argument('--print_interval', type=int, default=200)

    parser.add_argument('--optim', type=str, default='SGD')
    parser.add_argument('--batch_size', type=int, default=10)

    parser.add_argument('--k', type=int, default=5, help="Number of GANs to select teacher from")
    parser.add_argument('--num_particle_samples', type=int, default=100, help="Number of sample particles to aggregate fitness estimate over")
    parser.add_argument('--r_epochs', type=int, default=3, help="Number of epochs of GPO")

    parser.add_argument('--crossover_samples', type=int, default=1000, help="number of samples for crossover")

    args = parser.parse_args()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    _, X, Y = load_dataset("../unit_cell_data_16.csv")
    X = batch_dataset(X, args.batch_size)
    num_batches = len(X)

    _, _, _, evaluations = train_GPO_GAN(X, Y, num_batches, args.k, args.r_epochs)
