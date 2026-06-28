import math

import torch
import numpy as np
from cv2 import resize as cv2_resize
from torch.nn.functional import softmax

from vietocr.model.transformerocr import VietOCR
from vietocr.model.vocab import Vocab


def translate(img, model, max_seq_length=128, sos_token=1, eos_token=2):
    "data: BxCXHxW"
    model.eval()
    device = img.device

    with torch.no_grad():
        src = model.cnn(img)
        memory = model.transformer.forward_encoder(src)

        translated_sentence = [[sos_token] * len(img)]
        char_probs = [[1] * len(img)]

        max_length = 0

        while max_length <= max_seq_length and not all(np.any(np.asarray(translated_sentence).T == eos_token, axis=1)):

            tgt_inp = torch.LongTensor(translated_sentence).to(device)
            
#            output = model(img, tgt_inp, tgt_key_padding_mask=None)
#            output = model.transformer(src, tgt_inp, tgt_key_padding_mask=None)
            output, memory = model.transformer.forward_decoder(tgt_inp, memory)
            output = softmax(output, dim=-1)
            output = output.to('cpu')

            values, indices = torch.topk(output, 5)
            
            indices = indices[:, -1, 0]
            indices = indices.tolist()
            
            values = values[:, -1, 0]
            values = values.tolist()
            char_probs.append(values)

            translated_sentence.append(indices)   
            max_length += 1

            del output

        translated_sentence = np.asarray(translated_sentence).T
        
        char_probs = np.asarray(char_probs).T
        char_probs = np.multiply(char_probs, translated_sentence > 3)
        char_probs = np.sum(char_probs, axis=-1) / (char_probs > 0).sum(-1)
    
    return translated_sentence, char_probs


def build_model(config):
    vocab = Vocab(config['vocab'])
    device = config['device']
    
    model = VietOCR(len(vocab),
                    config['backbone'],
                    config['cnn'], 
                    config['transformer'],
                    config['seq_modeling'])
    
    model = model.to(device)

    return model, vocab


def resize(w, h, expected_height, image_min_width, image_max_width):
    new_w = int(expected_height * float(w) / float(h))
    round_to = 10
    new_w = math.ceil(new_w / round_to) * round_to
    new_w = max(new_w, image_min_width)
    new_w = min(new_w, image_max_width)

    return new_w, expected_height


def process_image(image, image_height, image_min_width, image_max_width):
    # img = image.convert('RGB')
    # w, h = img.size
    # new_w, image_height = resize(w, h, image_height, image_min_width, image_max_width)
    # img = img.resize((new_w, image_height), Image.LANCZOS)
    h, w = image.shape[:2]
    new_w, image_height = resize(w, h, image_height, image_min_width, image_max_width)
    image = cv2_resize(image, (new_w, image_height))[..., ::-1]
    image = image.transpose(2, 0, 1).astype(np.float32) / 255.
    return image


def process_input(image, image_height, image_min_width, image_max_width):
    img = process_image(image, image_height, image_min_width, image_max_width)
    img = torch.from_numpy(np.expand_dims(img, axis=0))
    return img
