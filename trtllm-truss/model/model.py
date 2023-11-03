import numpy as np
from client import UserData, TritonClient
from threading import Thread
from utils import prepare_grpc_tensor
from pathlib import Path
from itertools import count

TRITON_MODEL_REPOSITORY_PATH = Path("/packages/inflight_batcher_llm/")

class Model:
    def __init__(self, **kwargs):
        self._data_dir = kwargs["data_dir"]
        self._config = kwargs["config"]
        self._secrets = kwargs["secrets"]
        self._tensor_parallel_count = None
        self._request_id_counter = count(start=1)
        self.triton_client = None

    def load(self):
        self._tensor_parallel_count = self._config["model_metadata"].get("tensor_parallelism", 1)
        self.triton_client = TritonClient(self._data_dir, TRITON_MODEL_REPOSITORY_PATH, self._tensor_parallel_count)
        self.triton_client.load_server_and_model(
            env={
                "HUGGING_FACE_HUB_TOKEN": self._secrets["hf_access_token"],
                "triton_tokenizer_repository": self._config["model_metadata"]["tokenizer_repository"],
            }
        )

    def predict(self, model_input):
        model_name = "ensemble"
        user_data = UserData()
        stream_uuid = str(next(self._request_id_counter))

        prompt = model_input.get("text_input")
        output_len = model_input.get("output_len", 50)
        beam_width = model_input.get("beam_width", 1)
        bad_words_list = model_input.get("bad_words_list", [""])
        stop_words_list = model_input.get("stop_words_list", [""])
        repetition_penalty = model_input.get("repetition_penalty", 1.0)

        input0 = [[prompt]]
        input0_data = np.array(input0).astype(object)
        output0_len = np.ones_like(input0).astype(np.uint32) * output_len
        bad_words_list = np.array([bad_words_list], dtype=object)
        stop_words_list = np.array([stop_words_list], dtype=object)
        streaming = [[True]]
        streaming_data = np.array(streaming, dtype=bool)
        beam_width = [[beam_width]]
        beam_width_data = np.array(beam_width, dtype=np.uint32)
        repetition_penalty_data = np.array([[repetition_penalty]], dtype=np.float32)

        inputs = [
            prepare_grpc_tensor("text_input", input0_data),
            prepare_grpc_tensor("max_tokens", output0_len),
            prepare_grpc_tensor("bad_words", bad_words_list),
            prepare_grpc_tensor("stop_words", stop_words_list),
            prepare_grpc_tensor("stream", streaming_data),
            prepare_grpc_tensor("beam_width", beam_width_data),
            prepare_grpc_tensor("repetition_penalty", repetition_penalty_data)
        ]

        # Start GRPC stream in a separate thread
        stream_thread = Thread(
            target=self.triton_client.start_grpc_stream,
            args=(user_data, model_name, inputs, stream_uuid)
        )
        stream_thread.start()

        # Yield results from the queue
        for i in TritonClient.stream_predict(user_data):
            yield i

        # Clean up GRPC stream and thread
        self.triton_client.stop_grpc_stream(stream_uuid, stream_thread)