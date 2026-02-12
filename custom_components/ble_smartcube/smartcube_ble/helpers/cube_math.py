"""Minimal cube math helpers based on cstimer's CubieCube."""

from __future__ import annotations

from typing import List


class CubieCube:
    """Cubie representation with move application and facelet export."""

    c_facelet = [
        [8, 9, 20],  # URF
        [6, 18, 38],  # UFL
        [0, 36, 47],  # ULB
        [2, 45, 11],  # UBR
        [29, 26, 15],  # DFR
        [27, 44, 24],  # DLF
        [33, 53, 42],  # DBL
        [35, 17, 51],  # DRB
    ]
    e_facelet = [
        [5, 10],  # UR
        [7, 19],  # UF
        [3, 37],  # UL
        [1, 46],  # UB
        [32, 16],  # DR
        [28, 25],  # DF
        [30, 43],  # DL
        [34, 52],  # DB
        [23, 12],  # FR
        [21, 41],  # FL
        [50, 39],  # BL
        [48, 14],  # BR
    ]
    ct_facelet = [4, 13, 22, 31, 40, 49]

    move_cube: List["CubieCube"] = []

    def __init__(self) -> None:
        self.ca = [0, 1, 2, 3, 4, 5, 6, 7]
        self.ea = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]

    def init(self, ca: List[int], ea: List[int]) -> "CubieCube":
        self.ca = ca[:]
        self.ea = ea[:]
        return self

    @staticmethod
    def edge_mult(a: "CubieCube", b: "CubieCube", prod: "CubieCube") -> None:
        for ed in range(12):
            prod.ea[ed] = a.ea[b.ea[ed] >> 1] ^ (b.ea[ed] & 1)

    @staticmethod
    def corn_mult(a: "CubieCube", b: "CubieCube", prod: "CubieCube") -> None:
        for corn in range(8):
            ori = ((a.ca[b.ca[corn] & 7] >> 3) + (b.ca[corn] >> 3)) % 3
            prod.ca[corn] = (a.ca[b.ca[corn] & 7] & 7) | (ori << 3)

    @staticmethod
    def cube_mult(a: "CubieCube", b: "CubieCube", prod: "CubieCube") -> None:
        CubieCube.corn_mult(a, b, prod)
        CubieCube.edge_mult(a, b, prod)

    def to_perm(self) -> List[int]:
        f = list(range(54))
        for c in range(8):
            corner = self.ca[c] & 0x7
            ori = self.ca[c] >> 3
            for n in range(3):
                f[self.c_facelet[c][(n + ori) % 3]] = self.c_facelet[corner][n]
        for e in range(12):
            edge = self.ea[e] >> 1
            ori = self.ea[e] & 1
            for n in range(2):
                f[self.e_facelet[e][(n + ori) % 2]] = self.e_facelet[edge][n]
        return f

    def to_facelet(self) -> str:
        perm = self.to_perm()
        faces = []
        for i in range(54):
            faces.append("URFDLB"[perm[i] // 9])
        return "".join(faces)

    def from_facelet(self, facelet: str) -> "CubieCube" | int:
        centers = facelet[4] + facelet[13] + facelet[22] + facelet[31] + facelet[40] + facelet[49]
        f = []
        count = 0
        for i in range(54):
            idx = centers.find(facelet[i])
            if idx == -1:
                return -1
            f.append(idx)
            count += 1 << (idx << 2)
        if count != 0x999999:
            return -1

        for i in range(8):
            ori = 0
            while ori < 3:
                if f[self.c_facelet[i][ori]] in (0, 3):
                    break
                ori += 1
            col1 = f[self.c_facelet[i][(ori + 1) % 3]]
            col2 = f[self.c_facelet[i][(ori + 2) % 3]]
            for j in range(8):
                if col1 == self.c_facelet[j][1] // 9 and col2 == self.c_facelet[j][2] // 9:
                    self.ca[i] = j | (ori % 3 << 3)
                    break

        for i in range(12):
            for j in range(12):
                if f[self.e_facelet[i][0]] == self.e_facelet[j][0] // 9 and f[self.e_facelet[i][1]] == self.e_facelet[j][1] // 9:
                    self.ea[i] = j << 1
                    break
                if f[self.e_facelet[i][0]] == self.e_facelet[j][1] // 9 and f[self.e_facelet[i][1]] == self.e_facelet[j][0] // 9:
                    self.ea[i] = (j << 1) | 1
                    break
        return self

    def apply_move_index(self, move_index: int) -> None:
        tmp = CubieCube()
        CubieCube.cube_mult(self, self.move_cube[move_index], tmp)
        self.ca = tmp.ca
        self.ea = tmp.ea


def _init_move_cube() -> List[CubieCube]:
    move_cube = [CubieCube() for _ in range(18)]
    move_cube[0].init([3, 0, 1, 2, 4, 5, 6, 7], [6, 0, 2, 4, 8, 10, 12, 14, 16, 18, 20, 22])
    move_cube[3].init([20, 1, 2, 8, 15, 5, 6, 19], [16, 2, 4, 6, 22, 10, 12, 14, 8, 18, 20, 0])
    move_cube[6].init([9, 21, 2, 3, 16, 12, 6, 7], [0, 19, 4, 6, 8, 17, 12, 14, 3, 11, 20, 22])
    move_cube[9].init([0, 1, 2, 3, 5, 6, 7, 4], [0, 2, 4, 6, 10, 12, 14, 8, 16, 18, 20, 22])
    move_cube[12].init([0, 10, 22, 3, 4, 17, 13, 7], [0, 2, 20, 6, 8, 10, 18, 14, 16, 4, 12, 22])
    move_cube[15].init([0, 1, 11, 23, 4, 5, 18, 14], [0, 2, 4, 23, 8, 10, 12, 21, 16, 18, 7, 15])
    for axis in range(0, 18, 3):
        for power in range(2):
            CubieCube.cube_mult(move_cube[axis + power], move_cube[axis], move_cube[axis + power + 1])
    return move_cube


CubieCube.move_cube = _init_move_cube()
