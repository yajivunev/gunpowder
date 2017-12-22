import logging
import numpy as np

from gunpowder.ext import tensorflow as tf
from gunpowder.nodes.generic_predict import GenericPredict
from gunpowder.volume import ArrayType, Array
from gunpowder.tensorflow.local_server import LocalServer

logger = logging.getLogger(__name__)

class Predict(GenericPredict):
    '''Tensorflow implementation of :class:`gunpowder.nodes.Predict`.

    Args:

        meta_graph_basename: Basename of a tensorflow meta-graph storing the
            trained tensorflow graph (aka a checkpoint), as created by
            :class:`gunpowder.nodes.Train`, for example.

        inputs (dict): Dictionary from the names of input tensors in the
            network to :class:``ArrayType`` or batch attribute name as string.

        outputs (dict): Dictionary from the names of output tensors in the
            network to :class:``ArrayType``. New volumes will be generated by
            this node for each entry (if requested downstream).

        volume_specs (dict, optional): An optional dictionary of
            :class:`ArrayType` to :class:`ArraySpec` to set the volume specs
            of generated volumes (``outputs``). This is useful to set the
            ``voxel_size``, for example, if they differ from the voxel size of
            the input volumes. Only fields that are not ``None`` in the given
            :class:`ArraySpec` will be used.
    '''

    def __init__(
            self,
            meta_graph_basename,
            inputs,
            outputs,
            volume_specs=None):

        super(Predict, self).__init__(
            inputs,
            outputs,
            volume_specs,
            spawn_subprocess=False)
        self.meta_graph_basename = meta_graph_basename
        self.session = None
        self.graph = None

    def start(self):

        target = LocalServer.get_target()
        logger.info("Initializing tf session, connecting to %s...", target)

        self.graph = tf.Graph()
        self.session = tf.Session(
            target=target,
            graph=self.graph)

        with self.graph.as_default():
            self.__read_meta_graph()

    def predict(self, batch, request):

        logger.debug("predicting in batch %i", batch.id)

        volume_outputs = self.__collect_requested_outputs(request)
        inputs = self.__collect_provided_inputs(batch)

        # compute outputs
        outputs = self.session.run(volume_outputs, feed_dict=inputs)

        for volume_type in volume_outputs:
            spec = self.spec[volume_type].copy()
            spec.roi = request[volume_type].roi
            batch.volumes[volume_type] = Array(
                outputs[volume_type],
                spec)

        logger.debug("predicted in batch %i", batch.id)

    def stop(self):

        if self.session is not None:
            self.session.close()
            self.graph = None
            self.session = None

    def __read_meta_graph(self):

        logger.info("Reading meta-graph...")

        # read the meta-graph
        saver = tf.train.import_meta_graph(
            self.meta_graph_basename + '.meta',
            clear_devices=True)
        # restore variables
        saver.restore(self.session, self.meta_graph_basename)

    def __collect_requested_outputs(self, request):

        volume_outputs = {}

        for output_name, volume_type in self.outputs.items():
            if volume_type in request:
                volume_outputs[volume_type] = output_name

        return volume_outputs

    def __collect_provided_inputs(self, batch):

        inputs = {}

        for input_name, input_type in self.inputs.items():
            if isinstance(input_type, ArrayType):
                if input_type in batch.volumes:
                    inputs[input_name] = batch.volumes[input_type].data
                else:
                    logger.warn("batch does not contain %s, input %s will not "
                                "be set", input_type, input_name)
            elif isinstance(input_type, np.ndarray):
                inputs[input_name] = input_type
            elif isinstance(input_type, str):
                inputs[input_name] = getattr(batch, input_type)
            else:
                raise Exception(
                    "Unknown network input type {}, can't be given to "
                    "network".format(input_type))

        return inputs
