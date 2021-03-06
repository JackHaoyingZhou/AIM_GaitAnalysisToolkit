#!/usr/bin/env python
# //==============================================================================
# /*
#     Software License Agreement (BSD License)
#     Copyright (c) 2020, WPIGaitAnalysisToolKit
#     (www.aimlab.wpi.edu)

#     All rights reserved.

#     Redistribution and use in source and binary forms, with or without
#     modification, are permitted provided that the following conditions
#     are met:

#     * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.

#     * Redistributions in binary form must reproduce the above
#     copyright notice, this list of conditions and the following
#     disclaimer in the documentation and/or other materials provided
#     with the distribution.

#     * Neither the name of authors nor the names of its contributors may
#     be used to endorse or promote products derived from this software
#     without specific prior written permission.

#     THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#     "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#     LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
#     FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
#     COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
#     INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
#     BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#     LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#     CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
#     LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
#     ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#     POSSIBILITY OF SUCH DAMAGE.

#     \author    <http://www.aimlab.wpi.edu>
#     \author    <nagoldfarb@wpi.edu>
#     \author    Nathaniel Goldfarb
#     \version   0.1
# */
# //==============================================================================

import numpy as np
from lib.Vicon import Vicon
from lib.GaitCore.Core import Data as Data
from lib.GaitCore.Core import Newton as Newton
from lib.GaitCore.Core import Point as Point
from lib.GaitCore.Bio import Side as Side
from lib.GaitCore.Bio import Leg as Leg
from lib.GaitCore.Bio import Joint
from lib.Vicon import Markers
from lib.GaitCore.Core import utilities as ult
import math

import matplotlib.pyplot as plt


class ViconGaitingTrial(object):

    def __init__(self, vicon_file, dt=0.01):

        # self._notes_file = notes_file
        self.names = ["HipAngles", "KneeAngles", "AbsAnkleAngle"]
        self._dt = dt

        self._vicon = Vicon.Vicon(vicon_file)
        self.vicon_set_points = {}
        self._joint_trajs = None
        self._black_list = []
        self._use_black_list = False

        # Flag for if the data was gathered from the right leg hip angle
        # Data will only be gathered from the right leg iff handle_nan was set to True
        # and the data would otherwise have caused an abort
        self.gait_cycle_left_leg = True

        # self.create_index_seperators()

    def create_index_seperators(self, verbose=False, handle_nan=False, abort_nan=False):
        """
        This function find the index that seperates
        the sensors by the joints angles
        Sets the varibles:
        self.vicon_set_points
        self.exo_set_points
        :return: None
        """
        vicon = []

        model = self.vicon.get_model_output()
        hip = model.get_left_leg().hip.angle.x

        # Perform checks on the data according to flags set by user
        if False not in np.isnan(hip) or (abort_nan and True in np.isnan(hip)):
            # Make sure that we can use the data with our current configuration
            if verbose:
                if abort_nan:
                    print("The field left_leg.hip.angle.x contains at least one NaN!")
                else:
                    print("The field left_leg.hip.angle.x is composed entirely of NaNs!")
                if handle_nan:
                    print("Attempting to calculate gait cycles using the right leg...")
                else:
                    print("Aborting...")
            if handle_nan:
                # if handle_nan is set to True, we'll try to handle this automatically by using the right leg data
                hip = model.get_right_leg().hip.angle.x
                self.gait_cycle_left_leg = False
                if False not in np.isnan(hip) or (abort_nan and True in np.isnan(hip)):
                    if verbose:
                        if abort_nan:
                            print("The field right_leg.hip.angle.x contains at least one NaN!")
                        else:
                            print("The field right_leg.hip.angle.x is composed entirely of NaNs!")
                        print("Aborting...")
                    self.vicon_set_points = []
                    return
            else:
                self.vicon_set_points = []
                return

        if abort_nan and True in np.isnan(hip):
            if verbose:
                print("NaNs in dataset!")
                print("Aborting...")
            self.vicon_set_points = []
            return

        N = 10
        hip = np.convolve(hip, np.ones((N,)) / N, mode='valid')

        # plt.plot(hip)
        # plt.show()

        peaks = [max(0, value) for index, value in enumerate(hip)]
        # peaks is the data of hips, just floored at 0

        flag = False
        gait_borders = []
        highest = 0
        highest_ind = 0
        for i in range(len(peaks)):
            if peaks[i] == 0 or np.isnan(peaks[i]):
                if highest != 0 and flag:
                    gait_borders.append(highest_ind)
                    if verbose:
                        print("Peak detected! Highest point of peak is at index " + str(highest_ind))
                flag = True
                highest = 0
            else:
                if highest < peaks[i]:
                    highest = peaks[i]
                    highest_ind = i
        # gait_borders is an array of the highest values within each peak,
        # where a valid peak is defined as a peak which is not cut off by either the beginning or end of the data

        if len(gait_borders) < 2:  # if we have 1 or 0 peaks detected, there are no gait cycles
            if verbose:
                print("No gait cycles detected in data")
            self.vicon_set_points = []
            return

        for i in range(len(gait_borders) - 1):
            vicon.append((gait_borders[i], gait_borders[i + 1]))

        if verbose:
            print("Gait cycles: " + str(vicon))
        self.vicon_set_points = vicon  # varible that holds the setpoints for the vicon

    def get_stairs(self, toe_marker, step_frame):

        markers = self.vicon.get_markers()
        toe = markers.get_marker(toe_marker)
        stairA = markers.get_frame(step_frame)
        distA = []
        distB = []

        for i in range(len(toe)):
            distA.append(Markers.transform_vector(np.linalg.pinv(stairA[i]), toe[i].toarray())[2][0])

        error = 1.0
        start = distA[0]
        points = [0] * len(distA)
        searching = False
        N = 20
        distA = np.convolve(distA, np.ones((N,)) / N, mode='valid')
        local = []
        hills = []
        for ii in range(len(distA) - 3):

            d = distA[ii] - distA[ii + 3]

            if abs(d) > error and d < 0:
                searching = True
            else:
                searching = False
                if local:
                    if local[-1][1] > 150:
                        hills.append(local)
                        points[local[0][0]] = local[0][1]
                    local = []

            if searching:
                local.append((ii, distA[ii]))

        for hill in hills:

            max = hill[-1]
            current_index = max[0] + 3
            current_value = distA[current_index]
            current_index += 1

            while current_value >= distA[current_index]:
                current_value = distA[current_index]
                current_index += 1
                hill.append((current_index, distA[current_index]))
                points[current_index] = distA[current_index]

        return hills

    def get_force_plates(self):
        """
        Seperates then force plate data
        :return: Force plate data
        :rtype: Dict
        """
        joints = {}
        plate1 = self.vicon.get_force_plate(1)
        plate2 = self.vicon.get_force_plate(2)
        plate1_forces = plate1.get_forces()
        plate2_forces = plate2.get_forces()
        plate1_moments = plate1.get_moments()
        plate2_moments = plate2.get_moments()

        p1 = (1, plate1_forces, plate1_moments)
        p2 = (2, plate2_forces, plate2_moments)
        joints[1] = []
        joints[2] = []

        for p in (p1, p2):
            key = p[0]
            if self._use_black_list:
                if key in self._black_list:
                    continue
            plateF = p[1]
            plateM = p[2]
            for inc in self.vicon_set_points:
                start = plate1.get_offset_index(inc[0])
                end = plate1.get_offset_index(inc[1])
                Fx = np.array(plateF.x)[start:end]
                Fy = np.array(plateF.y)[start:end]
                Fz = np.array(plateF.z)[start:end]
                Mx = np.array(plateM.x)[start:end]
                My = np.array(plateM.y)[start:end]
                Mz = np.array(plateM.z)[start:end]
                f = Point.Point(Fx, Fy, Fz)
                m = Point.Point(Mx, My, Mz)
                data = Newton.Newton(None, f, m, None)
                time = (len(Fx) / float(self.vicon.length)) * self.dt
                stamp = Data.Data(data, np.linspace(0, time, len(data)))
                joints[key].append(stamp)

        return joints

    def get_joint_trajectories(self):
        """
        Seperates then joint trajs data
        :return: joint trajectory data
        :rtype: Dict
        """
        joints = {}
        count = 0
        model = self.vicon.get_model_output()
        for fnc, side in zip((model.get_left_leg(), model.get_right_leg()), ("L", "R")):
            for joint_name in ["_hip", "_knee", "_ankle"]:
                name = side + joint_name[1:]
                joints[name] = []
                for inc in self.vicon_set_points:
                    time = np.linspace(0, 1, (inc[1] - inc[0]))
                    current_joint = fnc.__dict__[joint_name]

                    angleX = Data.Data(np.array(current_joint.angle.x[inc[0]:inc[1]]), time)
                    angleY = Data.Data(np.array(current_joint.angle.y[inc[0]:inc[1]]), time)
                    angleZ = Data.Data(np.array(current_joint.angle.z[inc[0]:inc[1]]), time)
                    angle = Point.Point(x=angleX, y=angleY, z=angleZ)

                    powerX = Data.Data(np.array(current_joint.power.x[inc[0]:inc[1]]), time)
                    powerY = Data.Data(np.array(current_joint.power.y[inc[0]:inc[1]]), time)
                    powerZ = Data.Data(np.array(current_joint.power.z[inc[0]:inc[1]]), time)
                    power = Point.Point(x=powerX, y=powerY, z=powerZ)

                    torqueX = Data.Data(np.array(current_joint.moment.x[inc[0]:inc[1]]), time)
                    torqueY = Data.Data(np.array(current_joint.moment.y[inc[0]:inc[1]]), time)
                    torqueZ = Data.Data(np.array(current_joint.moment.z[inc[0]:inc[1]]), time)
                    torque = Point.Point(x=torqueX, y=torqueY, z=torqueZ)

                    forceX = Data.Data(np.array(current_joint.force.x[inc[0]:inc[1]]), time)
                    forceY = Data.Data(np.array(current_joint.force.y[inc[0]:inc[1]]), time)
                    forceZ = Data.Data(np.array(current_joint.force.z[inc[0]:inc[1]]), time)
                    force = Point.Point(forceX, forceY, forceZ)

                    stamp = Joint.Joint(angle, force, torque, power)
                    if self._use_black_list:
                        if count in self._black_list:
                            continue
                    joints[name].append(stamp)
                    count += 1

        left_leg = Leg.Leg(joints["Rhip"], joints["Rknee"], joints["Rankle"])
        right_leg = Leg.Leg(joints["Lhip"], joints["Lknee"], joints["Lankle"])
        body = Side.Side(left_leg, right_leg)
        return body

    def get_emg(self):
        """
       Seperates then EMGs data
       :return: EMGs data
       :rtype: Bio.side
        """
        joints = {}
        count = 0
        emgs = self.vicon.get_all_emgs()

        for key, emg in emgs.items():
            joints[key] = []
            for inc in self.vicon_set_points:
                start = emg.get_offset_index(inc[0])
                end = emg.get_offset_index(inc[1])
                data = np.array(emg.get_values())[start:end]
                time = (len(data) / float(self.vicon.length)) * self.dt
                stamp = Data.Data(data, np.linspace(0, time, len(data)))
                if self._use_black_list:
                    if count in self._black_list:
                        continue
                joints[key].append(stamp)

                count += 1

        return joints

    def get_T_emgs(self):
        """
       Seperates then EMGs data
       :return: EMGs data
       :rtype: Bio.side
        """
        joints = {}
        count = 0
        emgs = self.vicon.get_all_t_emg()

        for key, emg in emgs.items():
            joints[key] = []
            for inc in self.vicon_set_points:
                start = emg.get_offset_index(inc[0])
                end = emg.get_offset_index(inc[1])
                data = np.array(emg.get_values())[start:end]
                time = (len(data) / float(self.vicon.length)) * self.dt
                stamp = Data.Data(data, np.linspace(0, time, len(data)))
                if self._use_black_list:
                    if count in self._black_list:
                        continue
                joints[key].append(stamp)
                count += 1

        return joints

    def get_CoPs(self):
        """
       Seperates then CoP data
       :return: CoP data
       :rtype: Dict
        """

        left = []
        right = []
        count = 0
        left_cop = self.exoskeleton.left_leg.calc_CoP()
        right_cop = self.exoskeleton.right_leg.calc_CoP()

        left = []
        right = []

        for inc in self.exo_set_points:
            left_data = left_cop[inc[0]:inc[1]]
            right_data = right_cop[inc[0]:inc[1]]

            time = (len(left_data) / float(self.exoskeleton.length)) * self.dt
            stamp_left = Data.Data(left_data, np.linspace(0, time, len(left_data)))
            stamp_right = Data.Data(right_data, np.linspace(0, time, len(right_data)))

            if self._use_black_list:
                if count in self._black_list:
                    continue
                else:
                    left.append(stamp_left)
                    right.append(stamp_right)

            count += 1

        side = Side.Side(left, right)

        return side

    def get_FSRs(self):
        """
               Seperates FSR data
               :return: FSR data
               :rtype: Dict
        """

        left_fsr = self.exoskeleton.left_leg.ankle.FSRs
        right_fsr = self.exoskeleton.right_leg.ankle.FSRs

        left = []
        right = []

        for inc in self.exo_set_points:
            left_data = np.array(
                [[left_fsr[0].get_values()[inc[0]:inc[1]]],
                 [left_fsr[1].get_values()[inc[0]:inc[1]]],
                 [left_fsr[2].get_values()[inc[0]:inc[1]]]])

            right_data = np.array(
                [[right_fsr[0].get_values()[inc[0]:inc[1]]],
                 [right_fsr[1].get_values()[inc[0]:inc[1]]],
                 [right_fsr[2].get_values()[inc[0]:inc[1]]]])

            time = (len(left_data) / float(self.exoskeleton.length)) * self.dt
            stamp_left = Data.Data(left_data, np.linspace(0, time, len(left_data)))
            stamp_right = Data.Data(right_data, np.linspace(0, time, len(right_data)))

            # if self._use_black_list:
            #     if count in self._black_list:
            #         continue
            #     else:
            #         left.append(stamp_left)
            #         right.append(stamp_right)
            #
            # count += 1

        side = Side.Side(left, right)

        return side

    def get_pots(self):
        """
       Seperates Pot data
       :return: Pot data
       :rtype: Dict
        """
        left_leg = self.exoskeleton.left_leg
        right_leg = self.exoskeleton.right_leg

        left = []
        right = []
        count = 0

        for inc in self.exo_set_points:
            left_data = np.array(
                [[left_leg.hip.pot.get_values()[inc[0]:inc[1]]],
                 [left_leg.knee.pot.get_values()[inc[0]:inc[1]]],
                 [left_leg.ankle.pot.get_values()[inc[0]:inc[1]]]])

            right_data = np.array(
                [[right_leg.hip.pot.get_values()[inc[0]:inc[1]]],
                 [right_leg.knee.pot.get_values()[inc[0]:inc[1]]],
                 [right_leg.ankle.pot.get_values()[inc[0]:inc[1]]]])

            time = (len(left_data) / float(self.exoskeleton.length)) * self.dt

            stamp_left = Data.Data()
            stamp_right = Data.Data()
            stamp_right.data = right_data
            stamp_left.data = left_data
            stamp_left.time = np.linspace(0, time, len(left_data))
            stamp_right.time = np.linspace(0, time, len(right_data))

            if self._use_black_list:
                if count in self._black_list:
                    continue
                else:
                    left.append(stamp_left)
                    right.append(stamp_right)
            count += 1

        side = Side.Side(left, right)
        return side

    def get_accels(self):
        """
                Seperates then force plate data
                :return: Force plate data
                :rtype: Dict
                """
        left_leg = self.exoskeleton.left_leg
        right_leg = self.exoskeleton.right_leg

        left = []
        right = []
        count = 0
        for inc in self.exo_set_points:
            left_data = np.array(
                [[left_leg.hip.IMU.accel.get_values()[inc[0]:inc[1]]],
                 [left_leg.knee.IMU.accel.get_values()[inc[0]:inc[1]]],
                 [left_leg.ankle.IMU.accel.get_values()[inc[0]:inc[1]]]])

            right_data = np.array(
                [[right_leg.hip.IMU.accel.get_values()[inc[0]:inc[1]]],
                 [right_leg.knee.IMU.accel.get_values()[inc[0]:inc[1]]],
                 [right_leg.ankle.IMU.accel.get_values()[inc[0]:inc[1]]]])

            time = (len(left_data) / float(self.exoskeleton.length)) * self.dt

            stamp_left = Data.Data(left_data, np.linspace(0, time, len(left_data)))
            stamp_right = Data.Data(right_data, np.linspace(0, time, len(right_data)))

            if self._use_black_list:
                if count in self._black_list:
                    continue
                else:
                    left.append(stamp_left)
                    right.append(stamp_right)
            count += 1

        side = Side.Side(left, right)

        return side

    def get_gyros(self):
        """
                Seperates then force plate data
                :return: Force plate data
                :rtype: Dict
                """
        left_leg = self.exoskeleton.left_leg
        right_leg = self.exoskeleton.right_leg

        left = []
        right = []
        count = 0

        for inc in self.exo_set_points:
            left_data = np.array(
                [[left_leg.hip.IMU.gyro.get_values()[inc[0]:inc[1]]],
                 [left_leg.knee.IMU.gyro.get_values()[inc[0]:inc[1]]],
                 [left_leg.ankle.IMU.gyro.get_values()[inc[0]:inc[1]]]])

            right_data = np.array(
                [[right_leg.hip.IMU.gyro.get_values()[inc[0]:inc[1]]],
                 [right_leg.knee.IMU.gyro.get_values()[inc[0]:inc[1]]],
                 [right_leg.ankle.IMU.gyro.get_values()[inc[0]:inc[1]]]])

            time = (len(left_data) / float(self.exoskeleton.length)) * self.dt
            stamp_left = Data.Data(left_data, np.linspace(0, time, len(left_data)))
            stamp_right = Data.Data(right_data, np.linspace(0, time, len(right_data)))

            if self._use_black_list:
                if count in self._black_list:
                    continue
                else:
                    left.append(stamp_left)
                    right.append(stamp_right)
            count += 1

        side = Side.Side(left, right)
        return side

    @property
    def dt(self):
        return self._dt

    @property
    def exoskeleton(self):
        return self._exoskeleton

    @property
    def vicon(self):
        return self._vicon

    @property
    def joint_trajs(self):
        return self._joint_trajs

    @dt.setter
    def dt(self, value):
        self._dt = value

    @exoskeleton.setter
    def exoskeleton(self, value):
        self._exoskeleton = value

    @vicon.setter
    def vicon(self, value):
        self._vicon = value

    @joint_trajs.setter
    def joint_trajs(self, value):
        self._joint_trajs = value

    def add_to_blacklist(self, black_indexs):
        """
        Add a  blacklist
        :param index: index to add
        :return:
        """
        self._use_black_list = True
        self._black_list = black_indexs

    def remove_from_blacklist(self):
        """
        Remove the blacklist
        :param index: index to add
        :return:
        """
        self._use_black_list = False
        self._black_list = []


def calc_kinematics(trajectory, dt=0.01):
    # y = trajectory.data
    # time = trajectory.time
    T = []
    y = trajectory
    # dt = time[1] - time[0]
    yp = [0.0]
    ypp = [0.0, 0.0]
    yp = np.append(yp, np.divide(np.diff(y, 1), np.power(dt, 1)))
    ypp = np.append(ypp, np.divide(np.diff(y, 2), np.power(dt, 2)))

    T.append(np.array(y))
    T.append(np.array(yp))
    T.append(np.array(ypp))

    return T

    # def plot(self):
    #
    #     plotter = TrialExaminer.TrialExaminer()
    #     joints = self.get_joint_trajectories()
    #     plates = self.get_force_plates()
    #     cops = self.get_CoPs()
    #     emgs = self.get_emgs()
    #
    #     accel = self.robot.get_accel
    #     gyro = self.robot.get_gyro
    #     pot = self.robot.get_pot
    #     fsr = self.robot.get_fsr
    #     left_fsr = [fsr["FSR1_Left"], fsr["FSR2_Left"], fsr["FSR3_Left"]]
    #     right_fsr = [fsr["FSR1_Right"], fsr["FSR2_Right"], fsr["FSR3_Right"]]
    #
    #     for key, sensor in accel.items():
    #         accel = PT.Line_Graph.Line_Graph(sensor.name, sensor, 3, ["x", "y", "z"])
    #         plotter.addfig(accel)
    #
    #     for key, sensor in gyro.items():
    #         gyro = PT.Line_Graph.Line_Graph(sensor.name, sensor, 3, ["x", "y", "z"])
    #         plotter.addfig(gyro)
    #
    #     for key, sensor in pot.items():
    #         pot = PT.Line_Graph.Line_Graph(sensor.name, sensor, 1, ["z"])
    #         plotter.addfig(pot)
    #
    #     fsr_plot = PT.FSR_BarGraph.FSR_BarGraph("FSR", fsr.values())
    #     plotter.addfig(fsr_plot)
    #     #
    #     cop_plot = PT.CoP_Plotter.CoP_Plotter("CoP", left_fsr, right_fsr)
    #     plotter.addfig(cop_plot)


if __name__ == '__main__':
    vicon_file = "/home/nathaniel/git/Gait_Analysis_Toolkit/Utilities/Walking01.csv"
    config_file = "/home/nathaniel/git/exoserver/Config/sensor_list.yaml"
    exo_file = "/home/nathaniel/git/exoserver/Main/subject_1234_trial_1.csv"
    trial = ViconGaitingTrial(vicon_file, config_file, exo_file)
    joints = trial.seperate_joint_trajectories()
    plate = trial.seperate_force_plates()
    left, right = trial.seperate_CoP()
