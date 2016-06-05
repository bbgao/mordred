from itertools import groupby

import numpy as np

from ._base import Descriptor
from ._graph_matrix import DistanceMatrix


__all__ = (
    'InformationContent',
    'TotalIC', 'StructuralIC', 'BondingIC', 'ComplementaryIC',
    'ModifiedIC', 'ZModifiedIC',
)


class BFSTree(object):
    __slots__ = ('mol', 'tree', 'order', 'visited',)

    def __init__(self, mol, i):
        self.mol = mol
        self.tree = {i: ()}
        self.order = 0
        self.visited = set([i])

    def expand(self):
        self._expand(self.tree)
        self.order += 1

    def _expand(self, tree):
        for src, dst in list(tree.items()):
            self.visited.add(src)

            if dst is ():
                tree[src] = {
                    n.GetIdx(): ()
                    for n in self.mol.GetAtomWithIdx(src).GetNeighbors()
                    if n.GetIdx() not in self.visited
                }

            else:
                self._expand(dst)

    @property
    def code(self):
        return tuple(sorted(self._code(self.tree, None, ())))

    def _code(self, tree, before, trail):
        if len(tree) == 0:
            yield trail

        else:
            for src, dst in tree.items():

                code = []
                if before is not None:
                    code.append(self.mol.GetBondBetweenAtoms(before, src).GetBondType())

                a = self.mol.GetAtomWithIdx(src)
                code.append(a.GetAtomicNum())
                code.append(a.GetDegree())

                nxt = tuple(list(trail) + code)
                for t in self._code(dst, src, nxt):
                    yield t


def neighborhood_code(mol, i, order):
    if order == 0:
        return mol.GetAtomWithIdx(i).GetAtomicNum()

    tree = BFSTree(mol, i)
    for _ in range(order):
        tree.expand()
    return tree.code


class InformationContentBase(Descriptor):
    __slots__ = ('_order',)
    kekulize = True

    def __str__(self):
        return self._name + str(self._order)

    @classmethod
    def preset(cls):
        return (cls(o) for o in range(6))

    def as_key(self):
        return self.__class__, (self._order,)

    def __init__(self, order=0):
        self._order = order

    rtype = float


class Ag(InformationContentBase):
    __slots__ = ('_order',)

    @classmethod
    def preset(cls):
        return ()

    _name = 'Ag'

    def dependencies(self):
        return {'D': DistanceMatrix(self.explicit_hydrogens)}

    def calculate(self, D):
        atoms = [
            neighborhood_code(self.mol, i, self._order)
            for i in range(self.mol.GetNumAtoms())
        ]

        ad = {a: i for i, a in enumerate(atoms)}
        Ags = [(k, sum(1 for _ in g)) for k, g in groupby(sorted(atoms))]
        Nags = len(Ags)
        return (
            np.fromiter((ad[k] for k, _ in Ags), 'int', Nags),
            np.fromiter((ag for _, ag in Ags), 'float', Nags),
        )

    rtype = None


def _shannon_entropy_term(a):
    return a * np.log2(a)


shannon_entropy_term = np.vectorize(_shannon_entropy_term)


def shannon_entropy(a, w=1):
    N = np.sum(a)
    return -np.sum(w * shannon_entropy_term(a / N))


class InformationContent(InformationContentBase):
    r"""neighborhood information content descriptor.

    :type order: int
    :param order: order(number of edge) of subgraph
    """
    __slots__ = ()

    _name = 'IC'

    def dependencies(self):
        return {'iAgs': Ag(self._order)}

    def calculate(self, iAgs):
        _, Ags = iAgs
        return shannon_entropy(Ags)


class TotalIC(InformationContentBase):
    r"""neighborhood total information content descriptor.

    .. math::
        {\rm TIC}_m = A \cdot {\rm IC}_m

    :type order: int
    :param order: order(number of edge) of subgraph
    """
    __slots__ = ()

    _name = 'TIC'

    def dependencies(self):
        return {'ICm': InformationContent(self._order)}

    def calculate(self, ICm):
        A = self.mol.GetNumAtoms()

        return A * ICm


class StructuralIC(TotalIC):
    r"""structural information content descriptor.

    .. math::
        {\rm SIC}_m = \frac{{\rm IC}_m}{\log_2 A}

    :type order: int
    :param order: order(number of edge) of subgraph
    """
    __slots__ = ()

    _name = 'SIC'

    def calculate(self, ICm):
        d = np.log2(self.mol.GetNumAtoms())

        with self.rethrow_zerodiv():
            return ICm / d


class BondingIC(TotalIC):
    r"""bonding information content descriptor.

    .. math::
        {\rm BIC}_m = \frac{{\rm IC}_m}{\log_2 \sum^B_{b=1} \pi^{*}_b}

    :type order: int
    :param order: order(number of edge) of subgraph

    :returns: NaN when :math:`\sum^B_{b=1} \pi^{*}_b <= 0`
    """
    __slots__ = ()

    _name = 'BIC'

    def calculate(self, ICm):
        B = sum(b.GetBondTypeAsDouble() for b in self.mol.GetBonds())

        with self.rethrow_zerodiv():
            log2B = np.log2(B)
            return ICm / log2B


class ComplementaryIC(TotalIC):
    r"""complementary information content descriptor.

    .. math::
        {\rm CIC}_m = \log_2 A - {\rm IC}_m

    :type order: int
    :param order: order(number of edge) of subgraph
    """
    __slots__ = ()

    _name = 'CIC'

    def calculate(self, ICm):
        A = self.mol.GetNumAtoms()

        return np.log2(A) - ICm


class ModifiedIC(InformationContent):
    r"""modified information content index descriptor.

    :type order: int
    :param order: order(number of edge) of subgraph
    """
    __slots__ = ()

    _name = 'MIC'

    def calculate(self, iAgs):
        ids, Ags = iAgs
        w = np.vectorize(lambda i: self.mol.GetAtomWithIdx(int(i)).GetMass())(ids)
        return shannon_entropy(Ags, w)


class ZModifiedIC(InformationContent):
    r"""Z-modified information content index descriptor.

    :type order: int
    :param order: order(number of edge) of subgraph
    """
    __slots__ = ()

    _name = 'ZMIC'

    def calculate(self, iAgs):
        ids, Ags = iAgs
        w = Ags * np.vectorize(lambda i: self.mol.GetAtomWithIdx(int(i)).GetAtomicNum())(ids)
        return shannon_entropy(Ags, w)
