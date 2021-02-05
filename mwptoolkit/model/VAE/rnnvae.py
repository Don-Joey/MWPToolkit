import torch
from torch import nn

from mwptoolkit.module.Encoder.rnn_encoder import BasicRNNEncoder
from mwptoolkit.module.Decoder.rnn_decoder import BasicRNNDecoder
from mwptoolkit.module.Strategy.sampling import topk_sampling

class RNNVAE(nn.Module):
    r"""LSTMVAE is the first text generation model with VAE,
     we modify its architecture to fit all RNN type, and rename it as RNNVAE
    """

    def __init__(self, config, dataset):
        super(RNNVAE, self).__init__(config, dataset)

        # load parameters info
        self.vocab_size=config["vocab_size"]
        self.embedding_size = config['embedding_size']
        self.hidden_size = config['hidden_size']
        self.latent_size = config['latent_size']
        self.num_encoder_layers = config['num_encoder_layers']
        self.num_decoder_layers = config['num_decoder_layers']
        self.num_highway_layers = config['num_highway_layers']
        self.rnn_cell_type = config['rnn_cell_type']
        self.max_epoch = config['epochs']
        self.bidirectional = config['bidirectional']
        self.dropout_ratio = config['dropout_ratio']
        self.eval_generate_num = config['eval_generate_num']
        self.max_length = config['max_seq_length']

        self.num_directions = 2 if self.bidirectional else 1
        self.padding_token_idx = config["out_pad_token"]
        self.sos_token_idx = config["out_sos_token"]
        self.eos_token_idx = config["out_eos_token"]

        # define layers and loss
        self.token_embedder = nn.Embedding(self.vocab_size, self.embedding_size, padding_idx=self.padding_token_idx)

        self.encoder = BasicRNNEncoder(self.embedding_size, self.hidden_size, self.num_encoder_layers, self.rnn_cell_type,
                                       self.dropout_ratio, self.bidirectional)
        self.decoder = BasicRNNDecoder(self.embedding_size, self.hidden_size, self.num_decoder_layers, self.rnn_cell_type,
                                       self.dropout_ratio)

        self.dropout = nn.Dropout(self.dropout_ratio)
        self.vocab_linear = nn.Linear(self.hidden_size, self.vocab_size)
        self.loss = nn.CrossEntropyLoss(ignore_index=self.padding_token_idx, reduction='none')

        if self.rnn_cell_type == "lstm":
            self.hidden_to_mean = nn.Linear(self.num_directions * self.hidden_size, self.latent_size)
            self.hidden_to_logvar = nn.Linear(self.num_directions * self.hidden_size, self.latent_size)
            self.latent_to_hidden = nn.Linear(self.latent_size, 2 * self.hidden_size)
        elif self.rnn_cell_type == 'gru' or self.rnn_cell_type == 'rnn':
            self.hidden_to_mean = nn.Linear(self.num_directions * self.hidden_size, self.latent_size)
            self.hidden_to_logvar = nn.Linear(self.num_directions * self.hidden_size, self.latent_size)
            self.latent_to_hidden = nn.Linear(self.latent_size, 2 * self.hidden_size)
        else:
            raise ValueError("No such rnn type {} for RNNVAE.".format(self.rnn_type))

    def generate(self, eval_data):
        generate_corpus = []
        idx2token = eval_data.idx2token

        with torch.no_grad():
            for _ in range(self.eval_generate_num):
                if self.rnn_type == "lstm":
                    hidden_states = torch.randn(size=(1, 2 * self.hidden_size), device=self.device)
                    hidden_states = torch.chunk(hidden_states, 2, dim=-1)
                    h_0 = hidden_states[0].unsqueeze(0).expand(self.num_dec_layers, -1, -1).contiguous()
                    c_0 = hidden_states[1].unsqueeze(0).expand(self.num_dec_layers, -1, -1).contiguous()
                    hidden_states = (h_0, c_0)
                else:
                    hidden_states = torch.randn(size=(self.num_dec_layers, 1, self.hidden_size), device=self.device)
                # draw noise from standard gussian distribution
                generate_tokens = []
                input_seq = torch.LongTensor([[self.sos_token_idx]]).to(self.device)
                for _ in range(self.max_length):
                    decoder_input = self.token_embedder(input_seq)
                    outputs, hidden_states = self.decoder(input_embeddings=decoder_input, hidden_states=hidden_states)
                    token_logits = self.vocab_linear(outputs)
                    token_idx = topk_sampling(token_logits)
                    token_idx = token_idx.item()
                    if token_idx == self.eos_token_idx:
                        break
                    else:
                        generate_tokens.append(idx2token[token_idx])
                        input_seq = torch.LongTensor([[token_idx]]).to(self.device)
                generate_corpus.append(generate_tokens)
        return generate_corpus

    def forward(self, input_text,target_text,input_length,target_length, epoch_idx=0):
        # input_text = corpus['target_idx'][:, :-1]
        # target_text = corpus['target_idx'][:, 1:]
        # input_length = corpus['target_length'] - 1
        batch_size = input_text.size(0)

        input_emb = self.token_embedder(input_text)
        _, hidden_states = self.encoder(input_emb, input_length)

        if self.rnn_cell_type == "lstm":
            h_n, c_n = hidden_states
        elif self.rnn_cell_type == 'gru' or self.rnn_cell_type == 'rnn':
            h_n = hidden_states
        else:
            raise NotImplementedError("No such rnn type {} for RNNVAE.".format(self.rnn_type))

        if self.bidirectional:
            h_n = h_n.view(self.num_encoder_layers, 2, batch_size, self.hidden_size)
            h_n = h_n[-1]
            h_n = torch.cat([h_n[0], h_n[1]], dim=1)
        else:
            h_n = h_n[-1]

        mean = self.hidden_to_mean(h_n)
        logvar = self.hidden_to_logvar(h_n)

        z = torch.randn([batch_size, self.latent_size]).to(self.device)
        z = mean + z * torch.exp(0.5 * logvar)

        hidden = self.latent_to_hidden(z)

        if self.rnn_cell_type == "lstm":
            decoder_hidden = torch.chunk(hidden, 2, dim=-1)
            h_0 = decoder_hidden[0].unsqueeze(0).expand(self.num_decoder_layers, -1, -1).contiguous()
            c_0 = decoder_hidden[1].unsqueeze(0).expand(self.num_decoder_layers, -1, -1).contiguous()
            decoder_hidden = (h_0, c_0)
        else:
            decoder_hidden = hidden.unsqueeze(0).expand(self.num_decoder_layers, -1, -1).contiguous()

        input_emb = self.dropout(input_emb)
        outputs, hidden_states = self.decoder(input_embeddings=input_emb, hidden_states=decoder_hidden)
        token_logits = self.vocab_linear(outputs)

        return token_logits

    def calculate_nll_test(self, corpus, epoch_idx=0):
        input_text = corpus['target_idx'][:, :-1]
        target_text = corpus['target_idx'][:, 1:]
        input_length = corpus['target_length'] - 1
        batch_size = input_text.size(0)

        input_emb = self.token_embedder(input_text)
        _, hidden_states = self.encoder(input_emb, input_length)

        if self.rnn_type == "lstm":
            h_n, c_n = hidden_states
        elif self.rnn_type == 'gru' or self.rnn_type == 'rnn':
            h_n = hidden_states
        else:
            raise NotImplementedError("No such rnn type {} for RNNVAE.".format(self.rnn_type))

        if self.bidirectional:
            h_n = h_n.view(self.num_enc_layers, 2, batch_size, self.hidden_size)
            h_n = h_n[-1]
            h_n = torch.cat([h_n[0], h_n[1]], dim=1)
        else:
            h_n = h_n[-1]

        mean = self.hidden_to_mean(h_n)
        logvar = self.hidden_to_logvar(h_n)

        z = torch.randn([batch_size, self.latent_size]).to(self.device)
        z = mean + z * torch.exp(0.5 * logvar)

        hidden = self.latent_to_hidden(z)

        if self.rnn_type == "lstm":
            decoder_hidden = torch.chunk(hidden, 2, dim=-1)
            h_0 = decoder_hidden[0].unsqueeze(0).expand(self.num_dec_layers, -1, -1).contiguous()
            c_0 = decoder_hidden[1].unsqueeze(0).expand(self.num_dec_layers, -1, -1).contiguous()
            decoder_hidden = (h_0, c_0)
        else:
            decoder_hidden = hidden.unsqueeze(0).expand(self.num_dec_layers, -1, -1).contiguous()

        outputs, hidden_states = self.decoder(input_embeddings=input_emb, hidden_states=decoder_hidden)
        token_logits = self.vocab_linear(outputs)

        loss = self.loss(token_logits.view(-1, token_logits.size(-1)), target_text.contiguous().view(-1))
        loss = loss.reshape_as(target_text)

        loss = loss.sum(dim=1)
        return loss.mean()